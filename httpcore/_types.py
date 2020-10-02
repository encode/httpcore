"""
Type definitions for type checking purposes.
"""

from typing import List, Mapping, NamedTuple, Optional, Tuple, TypeVar, Union

T = TypeVar("T")
StrOrBytes = Union[str, bytes]
Origin = Tuple[bytes, bytes, int]
URL = Tuple[bytes, bytes, Optional[int], bytes]
Headers = List[Tuple[bytes, bytes]]
TimeoutDict = Mapping[str, Optional[float]]


class SocksProxyCredentials(NamedTuple):
    username: bytes = None
    password: bytes = None
    userid: bytes = None
