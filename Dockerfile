FROM dipdup/dipdup:6.5.4
COPY . .
RUN inject_pyproject
