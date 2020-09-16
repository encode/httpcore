"""
Type definitions for type checking purposes.
"""
from collections import namedtuple
from typing import List, Mapping, Optional, Tuple, TypeVar, Union

T = TypeVar("T")
StrOrBytes = Union[str, bytes]
Origin = Tuple[bytes, bytes, int]
URL = Tuple[bytes, bytes, Optional[int], bytes]
Headers = List[Tuple[bytes, bytes]]
TimeoutDict = Mapping[str, Optional[float]]
Socks = namedtuple("Socks", ["socks_type", "proxy_host", "proxy_port"])
