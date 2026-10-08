"""
Source abstractions for CHAI Information Acquisition Layer.

Defines the InformationSource protocol and BaseInformationSource class that all
information channels (Web, API, Model Knowledge, and future RAG) must implement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, List, Protocol, runtime_checkable

from backend.information.models import InformationItem

SOURCE_TYPE_WEB = "web"
SOURCE_TYPE_API = "api"
SOURCE_TYPE_MODEL = "model"
SOURCE_TYPE_RAG = "rag"


@runtime_checkable
class InformationSource(Protocol):
    """
    Protocol defining the contract for any information acquisition source in CHAI.
    """
    source_type: str

    async def acquire(
        self,
        query: str,
        context: Optional[str] = None,
    ) -> List[InformationItem]:
        """
        Acquires and returns normalized InformationItem objects.
        Must not raise uncaught exceptions that would crash the pipeline.
        """
        ...


class BaseInformationSource(ABC):
    """
    Abstract base class providing common helpers and enforcing the source contract.
    """
    source_type: str = "generic"

    @abstractmethod
    async def acquire(
        self,
        query: str,
        context: Optional[str] = None,
    ) -> List[InformationItem]:
        """
        Acquires information and normalizes it into a list of InformationItems.
        """
        pass


__all__ = [
    "InformationSource",
    "BaseInformationSource",
    "SOURCE_TYPE_WEB",
    "SOURCE_TYPE_API",
    "SOURCE_TYPE_MODEL",
    "SOURCE_TYPE_RAG",
]
