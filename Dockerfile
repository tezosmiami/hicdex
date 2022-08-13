FROM dipdup/dipdup:6.0.0
COPY . .
RUN inject_pyproject
