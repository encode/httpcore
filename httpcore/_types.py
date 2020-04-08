"""
Type definitions for type checking purposes.
"""

from typing import Dict, List, Optional, Tuple, Union

StrOrBytesType = Union[str, bytes]
OriginType = Tuple[bytes, bytes, int]
URLType = Tuple[bytes, bytes, int, bytes]
HeadersType = List[Tuple[bytes, bytes]]
TimeoutDictType = Dict[str, Optional[float]]
