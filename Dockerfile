FROM dipdup/dipdup:5.2
COPY . .
RUN inject_pyproject
