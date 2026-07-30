from scripts.check_architecture import check


def test_architecture_dependencies_point_inward():
    assert check() == []
