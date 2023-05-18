FROM dipdup/dipdup:6.5.6
COPY . .
RUN inject_pyproject
