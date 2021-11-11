import json

import httpcore


def test_request(httpbin):
    response = httpcore.request("GET", httpbin.url)
    assert response.status == 200


def test_stream(httpbin):
    with httpcore.stream("GET", httpbin.url) as response:
        assert response.status == 200


def test_request_with_content(httpbin):
    url = f"{httpbin.url}/post"
    response = httpcore.request("POST", url, content=b'{"hello":"world"}')
    assert response.status == 200
    assert json.loads(response.content)["json"] == {"hello": "world"}
