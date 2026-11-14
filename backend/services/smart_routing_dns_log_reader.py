from __future__ import annotations

from dataclasses import dataclass

from backend.ports.remote_command_executor import RemoteCommandExecutor


@dataclass(frozen=True, slots=True)
class SmartRoutingDnsLogCursor:
    inode: int
    offset: int


@dataclass(frozen=True, slots=True)
class SmartRoutingDnsLogReadResult:
    lines: tuple[str, ...]
    cursor: SmartRoutingDnsLogCursor
    reset: bool


class SmartRoutingDnsLogReader:
    """
    Incrementally reads a dnsmasq log file on OpenWrt.

    The cursor is owned by MaxVPN and must be persisted by the caller.
    File rotation/recreation/truncation automatically resets the offset.
    """

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        *,
        log_path: str = "/tmp/maxvpn-dns-events.log",
        max_read_bytes: int = 256 * 1024,
    ) -> None:
        if max_read_bytes <= 0:
            raise ValueError("max_read_bytes must be positive")

        self._executor = executor
        self._log_path = log_path
        self._max_read_bytes = max_read_bytes

    def current_cursor(self) -> SmartRoutingDnsLogCursor:
        """
        Return the current inode and byte size of the remote DNS log.

        This is used when the worker starts so that historical log entries
        are not replayed after a process restart.
        """
        stat = self._run(
            [
                "sh",
                "-c",
                (
                    "set -u; "
                    f"if [ ! -f {self._quote(self._log_path)} ]; then "
                    "printf '0 0\\n'; exit 0; fi; "
                    f"inode=$(ls -i {self._quote(self._log_path)} 2>/dev/null "
                    "| awk '{print $1}'); "
                    f"size=$(ls -ln {self._quote(self._log_path)} 2>/dev/null "
                    "| awk '{print $5}' || true); "
                    'inode=$(printf "%s" "$inode" | tr -d "[:space:]"); '
                    'size=$(printf "%s" "$size" | tr -d "[:space:]"); '
                    'if [ -n "$inode" ] && [ -n "$size" ]; then '
                    'printf "%s %s\\n" "$inode" "$size"; '
                    "else "
                    "printf '0 0\\n'; "
                    "fi"
                ),
            ],
        )

        metadata = (stat.stdout or "").strip().split()

        if len(metadata) != 2:
            raise RuntimeError(
                "OpenWrt Smart Routing DNS log cursor metadata is invalid: "
                f"{stat.stdout!r}"
            )

        return SmartRoutingDnsLogCursor(
            inode=int(metadata[0]),
            offset=int(metadata[1]),
        )

    def read(
        self,
        cursor: SmartRoutingDnsLogCursor | None = None,
    ) -> SmartRoutingDnsLogReadResult:
        stat = self._run(
            [
                "sh",
                "-c",
                (
                    "set -u; "
                    f"if [ ! -f {self._quote(self._log_path)} ]; then exit 0; fi; "
                    f"inode=$(ls -i {self._quote(self._log_path)} 2>/dev/null "
                    "| awk '{print $1}'); "
                    f"size=$(ls -ln {self._quote(self._log_path)} 2>/dev/null "
                    "| awk '{print $5}' || true); "
                    'inode=$(printf "%s" "$inode" | tr -d "[:space:]"); '
                    'size=$(printf "%s" "$size" | tr -d "[:space:]"); '
                    'if [ -n "$inode" ] && [ -n "$size" ]; then '
                    'printf "%s %s\\n" "$inode" "$size"; '
                    "fi"
                ),
            ],
        )

        metadata = (stat.stdout or "").strip().split()

        if len(metadata) != 2:
            return SmartRoutingDnsLogReadResult(
                lines=(),
                cursor=cursor or SmartRoutingDnsLogCursor(0, 0),
                reset=False,
            )

        inode = int(metadata[0])
        size = int(metadata[1])

        reset = cursor is not None and (cursor.inode != inode or cursor.offset > size)

        offset = 0 if cursor is None or reset else cursor.offset

        if offset == size:
            return SmartRoutingDnsLogReadResult(
                lines=(),
                cursor=SmartRoutingDnsLogCursor(inode, size),
                reset=reset,
            )

        block_size = 4096
        block_offset = offset // block_size
        byte_remainder = offset % block_size
        bytes_remaining = size - offset
        read_bytes = min(self._max_read_bytes, bytes_remaining)

        blocks_needed = (byte_remainder + read_bytes + block_size - 1) // block_size

        read_command = (
            f"dd if={self._quote(self._log_path)} "
            f"bs={block_size} "
            f"skip={block_offset} "
            f"count={blocks_needed} 2>/dev/null"
        )

        # dd with a large block size avoids the pathological O(offset)
        # behavior of bs=1. tail then discards the bytes preceding the
        # exact cursor position and limits the amount returned to the
        # configured chunk size.
        read_command += f" | tail -c +{byte_remainder + 1} | head -c {read_bytes}"

        result = self._run(
            [
                "sh",
                "-c",
                read_command,
            ],
        )

        data = result.stdout or ""

        # EOF can be determined from the authoritative remote file size,
        # not from stdout length, because the SSH executor strips stdout.
        remote_read_reached_eof = offset + read_bytes >= size

        # When dd reached the current end of file, the last line is complete
        # for this read even if the file does not end with a newline.
        #
        # When dd did not reach EOF, preserve an incomplete trailing line
        # and advance the cursor only through complete newline-terminated data.
        if remote_read_reached_eof:
            complete_data = data
            new_offset = size
        else:
            last_newline = data.rfind("\n")
            if last_newline < 0:
                return SmartRoutingDnsLogReadResult(
                    lines=(),
                    cursor=SmartRoutingDnsLogCursor(inode, offset),
                    reset=reset,
                )

            complete_data = data[: last_newline + 1]
            new_offset = offset + len(complete_data.encode("utf-8"))

        return SmartRoutingDnsLogReadResult(
            lines=tuple(complete_data.splitlines()),
            cursor=SmartRoutingDnsLogCursor(inode, new_offset),
            reset=reset,
        )

    def _run(self, command: list[str]):
        result = self._executor.run(command)

        if result.returncode != 0:
            raise RuntimeError(
                "OpenWrt Smart Routing DNS log command failed: "
                f"{command!r}; "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}",
            )

        return result

    @staticmethod
    def _quote(value: str) -> str:
        return "'" + value.replace("'", "'\"'\"'") + "'"
