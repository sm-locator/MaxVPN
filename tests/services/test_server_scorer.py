from backend.services.server_scorer import ServerScorer
from tests.factories import make_server
from backend.services.server_score_weights import ServerScoreWeights


def test_score_is_100_for_idle_server():
    scorer = ServerScorer()

    score = scorer.score(
        make_server(load=0),
    )

    assert score == 100


def test_score_decreases_with_load():
    scorer = ServerScorer()

    low = scorer.score(
        make_server(load=20),
    )

    high = scorer.score(
        make_server(load=70),
    )

    assert low > high


def test_score_never_negative():
    scorer = ServerScorer()

    score = scorer.score(
        make_server(load=150),
    )

    assert score == 0


def test_score_decreases_with_latency():
    scorer = ServerScorer()

    fast = scorer.score(
        make_server(load=20, latency=10),
    )

    slow = scorer.score(
        make_server(load=20, latency=80),
    )

    assert fast > slow


def test_load_has_higher_priority_than_latency():
    scorer = ServerScorer()

    low_load = scorer.score(
        make_server(load=10, latency=50),
    )

    high_load = scorer.score(
        make_server(load=40, latency=50),
    )

    assert low_load > high_load


def test_load_weight_affects_score():
    scorer = ServerScorer(ServerScoreWeights(load=2.0))

    score = scorer.score(make_server(load=20))

    assert score == 60


def test_latency_weight_affects_score():
    scorer = ServerScorer(ServerScoreWeights(latency=0.5))

    score = scorer.score(make_server(load=0, latency=20))

    assert score == 90


def test_combined_weights():
    scorer = ServerScorer(
        ServerScoreWeights(
            load=2.0,
            latency=0.5,
        )
    )

    score = scorer.score(
        make_server(
            load=10,
            latency=20,
        )
    )

    assert score == 70
