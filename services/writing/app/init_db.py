from app.database import Base, engine
from app.models import Essay

Base.metadata.create_all(bind=engine)

print("Tables created successfully")