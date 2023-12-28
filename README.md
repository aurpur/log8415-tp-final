# log8415-tp-final# log8415-project

## Setup

**Prerequisites:**

- [Python 3.12](https://www.python.org) (or later) 
- [Poetry](https://python-poetry.org/) (latest)

**AWS Credential**
- AWS credentials configured in `~/.aws/credentials`
- Lab's private SSH key copied to `labfinal.pem` at the project root, then run `chmod 600`

**Installation** 
```sh
# Install dependencies
poetry install
```

## Deploy

```sh
# Deploy one of the three architectures
poetry run python3 -m standalone
poetry run python3 -m cluster
poetry run python3 -m security
```

## Benchmark

**Prerequisites:**

- _standalone_ or _cluster_ deployment
- [sysbench](https://github.com/akopytov/sysbench)

```sh
./tools/benchmark.sh <mysql_host> <mysql_user> <mysql_password> <mysql_db>
```

## Cleanup

Terminate all project AWS resources.

```sh
poetry run python3 -m deploy.cleanup
```
