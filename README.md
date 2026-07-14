# GOA Platform

A multi-service backend architecture.

## Quick Start (Local Development)

This project uses Docker Compose to run all services locally.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ITI-OpenSource-Alex/GOA.git
   cd GOA
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   cp services/gateway/.env.example services/gateway/.env
   ```

   Add real provider keys to the root `.env` before running live AI evaluations.

3. **Start the infrastructure:**
   ```bash
   make up
   ```

*(Note for Windows users: The Makefile automatically handles MSYS path conversion for Docker volume mounts).*

4. **Verify:**
- Gateway Health: `curl http://localhost:8080/health`
- Grafana: `http://localhost:3001` (admin/admin)
