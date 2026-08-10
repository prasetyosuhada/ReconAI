# Import all SQLAlchemy models here so Alembic can discover their metadata
from app.db.base_class import Base  # noqa: F401
from app.models.coa import ChartOfAccount  # noqa: F401
from app.models.document import Document, DocumentExtraction  # noqa: F401
