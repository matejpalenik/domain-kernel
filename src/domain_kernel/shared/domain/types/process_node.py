"""Describe the nodes that can be connected by process flows."""

from __future__ import annotations

from domain_kernel.shared.domain.records.activity import Activity
from domain_kernel.shared.domain.records.event import Event
from domain_kernel.shared.domain.records.gateway import Gateway

type ProcessNode = Activity | Event | Gateway
