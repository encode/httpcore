from unittest.mock import MagicMock, patch

import pytest

from httpcore._backends.asyncio import SocketStream


class TestSocketStream:
    class TestIsReadable:
        @pytest.mark.asyncio
        async def test_returns_true_when_transport_has_no_socket(self):
            stream_reader = MagicMock()
            stream_reader._transport.get_extra_info.return_value = None
            sock_stream = SocketStream(stream_reader, MagicMock())

            assert sock_stream.is_readable()

        @pytest.mark.asyncio
        async def test_returns_true_when_socket_is_readable(self):
            stream_reader = MagicMock()
            stream_reader._transport.get_extra_info.return_value = MagicMock()
            sock_stream = SocketStream(stream_reader, MagicMock())

            with patch(
                "httpcore._utils.is_socket_readable", MagicMock(return_value=True)
            ):
                assert sock_stream.is_readable()
