"""Describe the nodes that can be connected by process flows."""

from __future__ import annotations

from domain_kernel.shared.domain.entities.activity import Activity
from domain_kernel.shared.domain.entities.event import Event
from domain_kernel.shared.domain.entities.gateway import Gateway

type ProcessNode = Activity | Event | Gateway
