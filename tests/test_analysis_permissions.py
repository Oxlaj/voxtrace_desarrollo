from backend.api.analisis import router


def test_analysis_endpoint_requires_all_analysis_roles() -> None:
    route = next(route for route in router.routes if route.path == "/analisis/identificacion")
    dependency = route.dependant.dependencies[-1]

    assert dependency.call.__name__ == "role_dependency"
    allowed_roles = dependency.call.__closure__[0].cell_contents
    assert allowed_roles == ("Administrador", "Investigador", "Analista")
