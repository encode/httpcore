import hpack
import hyperframe.frame
import pytest

import httpcore


@pytest.mark.anyio
async def test_http2_connection_with_trailing_headers():
    """
    Test that trailing headers are correctly received and processed.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.AsyncMockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            hyperframe.frame.DataFrame(stream_id=1, data=b"Hello, world!").serialize(),
            # Send trailing headers
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b"x-trailer-1", b"trailer-value-1"),
                        (b"x-trailer-2", b"trailer-value-2"),
                    ]
                ),
                flags=["END_HEADERS", "END_STREAM"],
            ).serialize(),
        ]
    )
    async with httpcore.AsyncHTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        response = await conn.request("GET", "https://example.com/")
        assert response.status == 200
        assert response.content == b"Hello, world!"

        # Check that trailing headers are included in extensions
        assert "trailing_headers" in response.extensions
        assert response.extensions["trailing_headers"] == [
            (b"x-trailer-1", b"trailer-value-1"),
            (b"x-trailer-2", b"trailer-value-2"),
        ]


@pytest.mark.anyio
async def test_http2_connection_with_body_and_trailing_headers():
    """
    Test that trailing headers are correctly received and processed
    when reading the response body in chunks.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.AsyncMockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            hyperframe.frame.DataFrame(stream_id=1, data=b"Hello, ").serialize(),
            hyperframe.frame.DataFrame(stream_id=1, data=b"world!").serialize(),
            # Send trailing headers
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b"x-trailer-1", b"trailer-value-1"),
                        (b"x-trailer-2", b"trailer-value-2"),
                    ]
                ),
                flags=["END_HEADERS", "END_STREAM"],
            ).serialize(),
        ]
    )

    async with httpcore.AsyncHTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        async with conn.stream("GET", "https://example.com/") as response:
            content = b""
            async for chunk in response.aiter_stream():
                content += chunk

            assert response.status == 200
            assert content == b"Hello, world!"

            # Check that trailing headers are included in extensions
            assert "trailing_headers" in response.extensions
            assert response.extensions["trailing_headers"] == [
                (b"x-trailer-1", b"trailer-value-1"),
                (b"x-trailer-2", b"trailer-value-2"),
            ]


@pytest.mark.anyio
async def test_http2_connection_with_trailing_headers_pseudo_removed():
    """
    Test that pseudo-headers in trailing headers are correctly filtered out.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.AsyncMockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            hyperframe.frame.DataFrame(stream_id=1, data=b"Hello, world!").serialize(),
            # Send trailing headers with a pseudo-header which should be filtered out
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":pseudo", b"should-be-filtered"),
                        (b"x-trailer", b"trailer-value"),
                    ]
                ),
                flags=["END_HEADERS", "END_STREAM"],
            ).serialize(),
        ]
    )
    async with httpcore.AsyncHTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        response = await conn.request("GET", "https://example.com/")
        assert response.status == 200
        assert response.content == b"Hello, world!"

        # Check that trailing headers are included in extensions but pseudo-headers are filtered
        assert "trailing_headers" in response.extensions
        assert len(response.extensions["trailing_headers"]) == 1
        assert response.extensions["trailing_headers"] == [
            (b"x-trailer", b"trailer-value"),
        ]
