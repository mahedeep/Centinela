"""Reexporta el esquema hijo del proceso B.

Las clases se definen en `common.py` porque `Decision`, `DocumentDecision` y
`CaseDetail` se referencian entre sí. Este módulo existe para que el import
`from centinela.schemas.documents import DocumentDecision` siga funcionando.
"""

from centinela.schemas.common import DocumentDecision, DocumentType, FieldValue

__all__ = ["DocumentDecision", "DocumentType", "FieldValue"]
