FROM dipdup/dipdup:6.5.5
COPY . .
RUN inject_pyproject
