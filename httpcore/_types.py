"""
Type definitions for type checking purposes.
"""
import enum
from typing import List, Mapping, NamedTuple, Optional, Tuple, TypeVar, Union

T = TypeVar("T")
StrOrBytes = Union[str, bytes]
Origin = Tuple[bytes, bytes, int]
URL = Tuple[bytes, bytes, Optional[int], bytes]
Headers = List[Tuple[bytes, bytes]]
TimeoutDict = Mapping[str, Optional[float]]

SocksProxyOrigin = Tuple[bytes, int]


class SocksProxyType(enum.Enum):
    socks5 = "socks5"
    socks4a = "socks4a"
    socks4 = "socks4"


class Socks4ProxyCredentials(NamedTuple):
    user_id: bytes


class Socks5ProxyCredentials(NamedTuple):
    username: bytes
    password: bytes


SocksProxyCredentials = Union[Socks4ProxyCredentials, Socks5ProxyCredentials, None]


class SocksProxyConfig(NamedTuple):
    proxy_type: SocksProxyType
    origin: SocksProxyOrigin
    auth_credentials: SocksProxyCredentials = None
