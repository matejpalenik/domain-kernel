"""Define the time source used to measure operation lease expiry."""

from collections.abc import Callable
from datetime import datetime

type Clock = Callable[[], datetime]
