FROM node:24-alpine AS frontend
WORKDIR /app/apps/nova
COPY apps/nova/package*.json ./
RUN npm ci
COPY apps/nova ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY services/api ./services/api
RUN pip install --no-cache-dir .
COPY --from=frontend /app/apps/nova/dist ./apps/nova/dist
ENV NOVA_DATABASE_URL=sqlite:////data/nova.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
