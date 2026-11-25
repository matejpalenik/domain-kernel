"""Identify a node in a descriptive process."""

from __future__ import annotations

from domain_kernel.modeling.domain.identifiers.activity_id import ActivityId
from domain_kernel.modeling.domain.identifiers.event_id import EventId
from domain_kernel.modeling.domain.identifiers.gateway_id import GatewayId

type ProcessNodeId = ActivityId | EventId | GatewayId
