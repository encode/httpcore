from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Iterable,
    Iterator,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)
from urllib.parse import urlparse

# Functions for typechecking...


HeadersAsSequence = Sequence[Tuple[Union[bytes, str], Union[bytes, str]]]
HeadersAsMapping = Mapping[Union[bytes, str], Union[bytes, str]]
HeaderTypes = Union[HeadersAsSequence, HeadersAsMapping, None]

Extensions = MutableMapping[str, Any]


def enforce_bytes(value: Union[bytes, str], *, name: str) -> bytes:
    """
    Any arguments that are ultimately represented as bytes can be specified
    either as bytes or as strings.

    However we enforce that any string arguments must only contain characters in
    the plain ASCII range. chr(0)...chr(127). If you need to use characters
    outside that range then be precise, and use a byte-wise argument.
    """
    if isinstance(value, str):
        try:
            return value.encode("ascii")
        except UnicodeEncodeError:
            raise TypeError(f"{name} strings may not include unicode characters.")
    elif isinstance(value, bytes):
        return value

    seen_type = type(value).__name__
    raise TypeError(f"{name} must be bytes or str, but got {seen_type}.")


def enforce_url(value: Union["URL", bytes, str], *, name: str) -> "URL":
    """
    Type check for URL parameters.
    """
    if isinstance(value, (bytes, str)):
        return URL(value)
    elif isinstance(value, URL):
        return value

    seen_type = type(value).__name__
    raise TypeError(f"{name} must be a URL, bytes, or str, but got {seen_type}.")


def enforce_headers(
    value: Union[HeadersAsMapping, HeadersAsSequence, None] = None, *, name: str
) -> List[Tuple[bytes, bytes]]:
    """
    Convienence function that ensure all items in request or response headers
    are either bytes or strings in the plain ASCII range.
    """
    if value is None:
        return []
    elif isinstance(value, Mapping):
        return [
            (
                enforce_bytes(k, name="header name"),
                enforce_bytes(v, name="header value"),
            )
            for k, v in value.items()
        ]
    elif isinstance(value, Sequence):
        return [
            (
                enforce_bytes(k, name="header name"),
                enforce_bytes(v, name="header value"),
            )
            for k, v in value
        ]

    seen_type = type(value).__name__
    raise TypeError(
        f"{name} must be a mapping or sequence of two-tuples, but got {seen_type}."
    )


def enforce_stream(
    value: Union[bytes, Iterable[bytes], AsyncIterable[bytes], None], *, name: str
) -> Union[Iterable[bytes], AsyncIterable[bytes]]:
    if value is None:
        return ByteStream(b"")
    elif isinstance(value, bytes):
        return ByteStream(value)
    return value


# * https://tools.ietf.org/html/rfc3986#section-3.2.3
# * https://url.spec.whatwg.org/#url-miscellaneous
# * https://url.spec.whatwg.org/#scheme-state
DEFAULT_PORTS = {
    b"ftp": 21,
    b"http": 80,
    b"https": 443,
    b"ws": 80,
    b"wss": 443,
}


def include_request_headers(
    headers: List[Tuple[bytes, bytes]],
    *,
    url: "URL",
    content: Union[None, bytes, Iterable[bytes], AsyncIterable[bytes]],
) -> List[Tuple[bytes, bytes]]:
    headers_set = {k.lower() for k, v in headers}

    if b"host" not in headers_set:
        default_port = DEFAULT_PORTS.get(url.scheme)
        if url.port is None or url.port == default_port:
            header_value = url.host
        else:
            header_value = b"%b:%d" % (url.host, url.port)
        headers = [(b"Host", header_value)] + headers

    if (
        content is not None
        and b"content-length" not in headers_set
        and b"transfer-encoding" not in headers_set
    ):
        if isinstance(content, bytes):
            content_length = str(len(content)).encode("ascii")
            headers += [(b"Content-Length", content_length)]
        else:
            headers += [(b"Transfer-Encoding", b"chunked")]  # pragma: nocover

    return headers


# Interfaces for byte streams...


class ByteStream:
    """
    A container for non-streaming content, and that supports both sync and async
    stream iteration.
    """

    def __init__(self, content: bytes) -> None:
        self._content = content

    def __iter__(self) -> Iterator[bytes]:
        yield self._content

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._content

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} [{len(self._content)} bytes]>"


class Origin:
    def __init__(self, scheme: bytes, host: bytes, port: int) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, Origin)
            and self.scheme == other.scheme
            and self.host == other.host
            and self.port == other.port
        )

    def __str__(self) -> str:
        scheme = self.scheme.decode("ascii")
        host = self.host.decode("ascii")
        port = str(self.port)
        return f"{scheme}://{host}:{port}"


class URL:
    """
    Represents the URL against which an HTTP request may be made.

    The URL may either be specified as a plain string, for convienence:

    ```python
    url = httpcore.URL("https://www.example.com/")
    ```

    Or be constructed with explicitily pre-parsed components:

    ```python
    url = httpcore.URL(scheme=b'https', host=b'www.example.com', port=None, target=b'/')
    ```

    Using this second more explicit style allows integrations that are using
    `httpcore` to pass through URLs that have already been parsed in order to use
    libraries such as `rfc-3986` rather than relying on the stdlib. It also ensures
    that URL parsing is treated identically at both the networking level and at any
    higher layers of abstraction.

    The four components are important here, as they allow the URL to be precisely
    specified in a pre-parsed format. They also allow certain types of request to
    be created that could not otherwise be expressed.

    For example, an HTTP request to `http://www.example.com/` forwarded via a proxy
    at `http://localhost:8080`...

    ```python
    # Constructs an HTTP request with a complete URL as the target:
    # GET https://www.example.com/ HTTP/1.1
    url = httpcore.URL(
        scheme=b'http',
        host=b'localhost',
        port=8080,
        target=b'https://www.example.com/'
    )
    request = httpcore.Request(
        method="GET",
        url=url
    )
    ```

    Another example is constructing an `OPTIONS *` request...

    ```python
    # Constructs an 'OPTIONS *' HTTP request:
    # OPTIONS * HTTP/1.1
    url = httpcore.URL(scheme=b'https', host=b'www.example.com', target=b'*')
    request = httpcore.Request(method="OPTIONS", url=url)
    ```

    This kind of request is not possible to formulate with a URL string,
    because the `/` delimiter is always used to demark the target from the
    host/port portion of the URL.

    For convenience, string-like arguments may be specified either as strings or
    as bytes. However, once a request is being issue over-the-wire, the URL
    components are always ultimately required to be a bytewise representation.

    In order to avoid any ambiguity over character encodings, when strings are used
    as arguments, they must be strictly limited to the ASCII range `chr(0)`-`chr(127)`.
    If you require a bytewise representation that is outside this range you must
    handle the character encoding directly, and pass a bytes instance.
    """

    def __init__(
        self,
        url: Union[bytes, str] = "",
        *,
        scheme: Union[bytes, str] = b"",
        host: Union[bytes, str] = b"",
        port: Optional[int] = None,
        target: Union[bytes, str] = b"",
    ) -> None:
        """
        Parameters:
            url: The complete URL as a string or bytes.
            scheme: The URL scheme as a string or bytes.
                Typically either `"http"` or `"https"`.
            host: The URL host as a string or bytes. Such as `"www.example.com"`.
            port: The port to connect to. Either an integer or `None`.
            target: The target of the HTTP request. Such as `"/items?search=red"`.
        """
        if url:
            parsed = urlparse(enforce_bytes(url, name="url"))
            self.scheme = parsed.scheme
            self.host = parsed.hostname or b""
            self.port = parsed.port
            self.target = (parsed.path or b"/") + (
                b"?" + parsed.query if parsed.query else b""
            )
        else:
            self.scheme = enforce_bytes(scheme, name="scheme")
            self.host = enforce_bytes(host, name="host")
            self.port = port
            self.target = enforce_bytes(target, name="target")

    @property
    def origin(self) -> Origin:
        default_port = {
            b"http": 80,
            b"https": 443,
            b"ws": 80,
            b"wss": 443,
            b"socks5": 1080,
        }[self.scheme]
        return Origin(
            scheme=self.scheme, host=self.host, port=self.port or default_port
        )

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, URL)
            and other.scheme == self.scheme
            and other.host == self.host
            and other.port == self.port
            and other.target == self.target
        )

    def __bytes__(self) -> bytes:
        if self.port is None:
            return b"%b://%b%b" % (self.scheme, self.host, self.target)
        return b"%b://%b:%d%b" % (self.scheme, self.host, self.port, self.target)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(scheme={self.scheme!r}, "
            f"host={self.host!r}, port={self.port!r}, target={self.target!r})"
        )


class Request:
    """
    An HTTP request.
    """

    def __init__(
        self,
        method: Union[bytes, str],
        url: Union[URL, bytes, str],
        *,
        headers: HeaderTypes = None,
        content: Union[bytes, Iterable[bytes], AsyncIterable[bytes], None] = None,
        extensions: Optional[Extensions] = None,
    ) -> None:
        """
        Parameters:
            method: The HTTP request method, either as a string or bytes.
                For example: `GET`.
            url: The request URL, either as a `URL` instance, or as a string or bytes.
                For example: `"https://www.example.com".`
            headers: The HTTP request headers.
            content: The content of the request body.
            extensions: A dictionary of optional extra information included on
                the request. Possible keys include `"timeout"`, and `"trace"`.
        """
        self.method: bytes = enforce_bytes(method, name="method")
        self.url: URL = enforce_url(url, name="url")
        self.headers: List[Tuple[bytes, bytes]] = enforce_headers(
            headers, name="headers"
        )
        self.stream: Union[Iterable[bytes], AsyncIterable[bytes]] = enforce_stream(
            content, name="content"
        )
        self.extensions = {} if extensions is None else extensions

        if "target" in self.extensions:
            self.url = URL(
                scheme=self.url.scheme,
                host=self.url.host,
                port=self.url.port,
                target=self.extensions["target"],
            )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} [{self.method!r}]>"


class Response:
    """
    An HTTP response.
    """

    def __init__(
        self,
        status: int,
        *,
        headers: HeaderTypes = None,
        content: Union[bytes, Iterable[bytes], AsyncIterable[bytes], None] = None,
        extensions: Optional[Extensions] = None,
    ) -> None:
        """
        Parameters:
            status: The HTTP status code of the response. For example `200`.
            headers: The HTTP response headers.
            content: The content of the response body.
            extensions: A dictionary of optional extra information included on
                the responseself.Possible keys include `"http_version"`,
                `"reason_phrase"`, and `"network_stream"`.
        """
        self.status: int = status
        self.headers: List[Tuple[bytes, bytes]] = enforce_headers(
            headers, name="headers"
        )
        self.stream: Union[Iterable[bytes], AsyncIterable[bytes]] = enforce_stream(
            content, name="content"
        )
        self.extensions = {} if extensions is None else extensions

        self._stream_consumed = False

    @property
    def content(self) -> bytes:
        if not hasattr(self, "_content"):
            if isinstance(self.stream, Iterable):
                raise RuntimeError(
                    "Attempted to access 'response.content' on a streaming response. "
                    "Call 'response.read()' first."
                )
            else:
                raise RuntimeError(
                    "Attempted to access 'response.content' on a streaming response. "
                    "Call 'await response.aread()' first."
                )
        return self._content

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} [{self.status}]>"

    # Sync interface...

    def read(self) -> bytes:
        if not isinstance(self.stream, Iterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to read an asynchronous response using 'response.read()'. "
                "You should use 'await response.aread()' instead."
            )
        if not hasattr(self, "_content"):
            self._content = b"".join([part for part in self.iter_stream()])
        return self._content

    def iter_stream(self) -> Iterator[bytes]:
        if not isinstance(self.stream, Iterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to stream an asynchronous response using 'for ... in "
                "response.iter_stream()'. "
                "You should use 'async for ... in response.aiter_stream()' instead."
            )
        if self._stream_consumed:
            raise RuntimeError(
                "Attempted to call 'for ... in response.iter_stream()' more than once."
            )
        self._stream_consumed = True
        yield from self.stream

    def close(self) -> None:
        if not isinstance(self.stream, Iterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to close an asynchronous response using 'response.close()'. "
                "You should use 'await response.aclose()' instead."
            )
        if hasattr(self.stream, "close"):
            self.stream.close()

    # Async interface...

    async def aread(self) -> bytes:
        if not isinstance(self.stream, AsyncIterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to read an synchronous response using "
                "'await response.aread()'. "
                "You should use 'response.read()' instead."
            )
        if not hasattr(self, "_content"):
            self._content = b"".join([part async for part in self.aiter_stream()])
        return self._content

    async def aiter_stream(self) -> AsyncIterator[bytes]:
        if not isinstance(self.stream, AsyncIterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to stream an synchronous response using 'async for ... in "
                "response.aiter_stream()'. "
                "You should use 'for ... in response.iter_stream()' instead."
            )
        if self._stream_consumed:
            raise RuntimeError(
                "Attempted to call 'async for ... in response.aiter_stream()' "
                "more than once."
            )
        self._stream_consumed = True
        async for chunk in self.stream:
            yield chunk

    async def aclose(self) -> None:
        if not isinstance(self.stream, AsyncIterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to close a synchronous response using "
                "'await response.aclose()'. "
                "You should use 'response.close()' instead."
            )
        if hasattr(self.stream, "aclose"):
            await self.stream.aclose()
