from server import app


def test_server_routes_are_stable():
    routes = {
        (route.method, route.resource.canonical)
        for route in app.router.routes()
    }

    assert ("POST", "/check") in routes
    assert ("GET", "/logs") in routes
    assert ("GET", "/logs/ws") in routes
