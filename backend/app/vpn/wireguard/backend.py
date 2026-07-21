from app.vpn.base import BaseVPNBackend


class WireGuardBackend(BaseVPNBackend):
    def generate_keys(self):
        raise NotImplementedError

    def allocate_ip(self):
        raise NotImplementedError

    def generate_config(self, client):
        raise NotImplementedError

    def generate_qr(self, client):
        raise NotImplementedError

    def add_client(self, client):
        raise NotImplementedError

    def remove_client(self, client):
        raise NotImplementedError

    def reload(self):
        raise NotImplementedError
