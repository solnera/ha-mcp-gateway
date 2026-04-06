"""Tests for MCP Gateway type definitions."""

from __future__ import annotations

from custom_components.mcp_gateway.types import DeviceDescription


def test_device_description_to_dict() -> None:
    """Test DeviceDescription.to_dict excludes None values."""
    desc = DeviceDescription(
        brand="Acme",
        model="LED-100",
        alias="Bedroom Light",
        device_id="abc123",
    )
    result = desc.to_dict()

    assert result == {
        "brand": "Acme",
        "model": "LED-100",
        "alias": "Bedroom Light",
        "device_id": "abc123",
    }
    assert "device_type" not in result
    assert "serial" not in result
    assert "mac" not in result
    assert "description" not in result


def test_device_description_to_dict_empty() -> None:
    """Test DeviceDescription.to_dict with all None values."""
    desc = DeviceDescription()
    result = desc.to_dict()

    assert result == {}


def test_device_description_to_dict_all_fields() -> None:
    """Test DeviceDescription.to_dict with all fields set."""
    desc = DeviceDescription(
        device_type="light",
        brand="Acme",
        model="LED-100",
        alias="Bedroom",
        description="A smart light",
        device_id="abc",
        serial="SN123",
        mac="AA:BB:CC:DD:EE:FF",
    )
    result = desc.to_dict()

    assert len(result) == 8
    assert result["device_type"] == "light"
    assert result["mac"] == "AA:BB:CC:DD:EE:FF"
