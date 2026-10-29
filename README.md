# Demand Agent Ingestion

A Python module for the **AI Multi-Agent Supply Chain Management System**. This module is intended to collect external data (starting with weather data), validate and normalize it, and make it available to downstream demand-prediction and supply-chain components.

> **Project status:** This README documents the setup and folder structure observed so far. It separates confirmed setup work from functionality that is planned or still needs verification. A folder's presence does not, by itself, mean that its functionality has been implemented.

## 1. Project purpose

The larger supply-chain system is intended to support decisions such as forecasting product demand, planning inventory, choosing warehouses and suppliers, and organizing deliveries. External signals such as temperature, rainfall and humidity may help the Demand Agent understand changes in customer demand across Kolkata and its surrounding regions.

The `demand_agent_ingestion` module is the data-entry stage for external information. Its intended responsibilities are to:

1. Retrieve information from an external source, such as a weather API.
2. Handle request failures and timeouts safely.
3. Validate the received fields and convert the response to a consistent internal structure.
4. Prepare valid records for storage, configured here to use MongoDB.
5. Make the ingestion logic testable and reusable by other parts of the system.

The high-level target flow is:

```text
External weather service
          |
          v
Weather/API adapter
          |
          v
Validation and normalization
          |
          v
Database/storage integration (MongoDB is configured)
          |
          v
Downstream Demand Agent / forecasting workflow
```

This is the intended architecture, not a claim that every stage has already been implemented or integration-tested.

## 2. Work completed so far

Based on the terminal output and checks shared during setup, the following items have been established:

- The working project directory is `D:\ai-multi-agent-supply-chain\demand_agent_ingestion`.
- A Python virtual environment exists in `.venv` and was activated from Windows CMD.
- The project is recognized by pip as `demand-agent-ingestion` version `0.1.0` and is installed in **editable mode** from the local project directory.
- The project configuration file `pyproject.toml` is part of the setup and was used as a project configuration/dependency file. Its exact declared dependency list still needs to be reviewed directly.
- A configuration-loading command imported `get_settings` from `demand_ingestion.config` and was used to inspect settings such as the application environment, MongoDB database name, HTTP timeout and retry-related configuration.
- The installed package list was inspected with `python -m pip list`.
- `python -m pip check` returned `No broken requirements found.`
- An invalid-distribution warning referring to `~ip` was investigated. The two leftover directories, `~ip` and `~ip-26.2.1.dist-info`, were removed, and the user confirmed that the warning no longer appears.

### What is not yet confirmed

The details available so far do **not** establish that the following components are complete or tested:

- A working Open-Meteo weather adapter.
- A successful live HTTP request to a weather service.
- A working MongoDB connection or successful database writes.
- An implemented or scheduled DAG workflow.
- A complete automated test suite.
- An end-to-end ingestion run that retrieves, validates and stores weather records.

These should be marked complete only after the corresponding code and test results are inspected.

## 3. Directory structure

The folder tree captured so far shows this structure. `tree /A` lists directories only; it does not display all files, so descriptions below explain the observed folders and their intended roles.

```text
demand_agent_ingestion/
├── .venv/
│   ├── Include/
│   ├── Lib/
│   │   └── site-packages/
│   └── Scripts/
├── dags/
├── docs/
├── scripts/
├── src/
│   ├── demand_agent_ingestion.egg-info/
│   └── demand_ingestion/
│       └── __pycache__/
├── tests/
└── pyproject.toml
```

The tree above is a concise guide, not a complete file inventory. More files may exist inside these directories than the directory-only listing showed.

### 3.1 `.venv/` — local Python environment

**Purpose:** Keeps the Python packages for this project separate from packages used by other Python projects on the computer.

- `Scripts/` contains Windows executables and activation scripts, including the virtual environment's Python and pip launchers.
- `Lib/site-packages/` contains installed Python packages and their package metadata.
- `Include/` is used by some Python packages that need header files during compilation or installation.

Activate the environment in Windows CMD from the project root:

```cmd
.venv\Scripts\activate.bat
```

The prompt should begin with `(.venv)` when it is active.

**Important:** Do not put application source code in `.venv/`, and normally do not commit this directory to version control. The environment can be recreated from the project configuration and dependency declarations.

### 3.2 `dags/` — workflow definitions

**Intended purpose:** Holds DAG (Directed Acyclic Graph) definitions if the project uses a workflow orchestrator such as Apache Airflow.

A DAG describes tasks, their order and their dependencies. A future ingestion workflow could, for example, request weather data, validate it, and then persist the valid records.

**Current evidence:** The directory exists. The folder name alone does not prove that Airflow is installed or that a DAG has been implemented. Inspect its files and the project configuration before choosing or configuring a scheduler.

### 3.3 `docs/` — human-readable documentation

**Intended purpose:** Stores documentation that explains how to install, configure, run, test and troubleshoot the module.

Useful documents may include:

- Setup instructions and command examples.
- Configuration-variable descriptions.
- Weather source/API details and expected response fields.
- MongoDB database/collection design.
- Data validation rules and troubleshooting notes.

This root `README.md` is the main introduction. More detailed design notes can live in `docs/` as the implementation grows.

### 3.4 `scripts/` — helper commands and utility programs

**Intended purpose:** Holds small runnable helpers for development and maintenance tasks.

Possible examples include a configuration check, a manual ingestion runner, a database connectivity check, or a historical-data import utility. These are examples only; they are not confirmed as existing scripts.

Keep reusable business logic in `src/demand_ingestion/`. A helper script should usually call that logic rather than duplicate the implementation.

### 3.5 `src/` — installable application source

**Purpose:** Contains the Python package that implements the module. This is a common “src layout”, which separates importable application code from tests, documentation and tooling.

#### `src/demand_ingestion/` — Python import package

This is the package namespace used by the configuration import seen during setup:

```python
from demand_ingestion.config import get_settings
```

This confirms that Python code is importing a `config` module under `demand_ingestion`. In this module, configuration loading is intended to provide settings such as the application environment, MongoDB database name, HTTP timeout and retry behaviour.

As the module develops, responsibilities can be separated into focused components, for example:

- **Configuration:** read and validate settings from the environment or a `.env` file.
- **Weather/API adapter:** make HTTP requests and handle API response/error cases.
- **Validation/normalization:** check required fields and standardize units, timestamps and data types.
- **Storage integration:** write valid records to MongoDB.
- **Ingestion orchestration:** call the components in the correct order.

These are recommended responsibilities, not a guaranteed list of existing modules. Inspect the files before creating new ones so existing work is preserved.

#### `src/demand_ingestion/__pycache__/` — Python bytecode cache

Python may create this directory automatically when it imports modules. It contains cached bytecode files to make later imports faster. It is generated by Python, not where source code should be written. It is normally safe to exclude from version control.

#### `src/demand_agent_ingestion.egg-info/` — package metadata

This metadata directory is generated by Python packaging/install tooling. It records information about the installed distribution, such as its name, version and dependency metadata. The observed distribution name is `demand-agent-ingestion`, while the import package name is `demand_ingestion`; distribution and import names are allowed to differ.

Do not put business logic in `*.egg-info`. Packaging tools may recreate or update this folder.

### 3.6 `tests/` — automated tests

**Purpose:** Contains tests that check expected behaviour without requiring every case to be checked manually.

As functionality is added, tests can cover:

- Configuration loading and invalid/missing settings.
- Weather adapter success, timeout, HTTP error and malformed responses.
- Validation of missing, incorrect or out-of-range weather fields.
- MongoDB writes and error handling (using an appropriate test database or mocks).
- Ingestion flow behaviour when an upstream service fails.

`pytest` is installed in the current environment. The existence of `tests/` does not by itself prove that test files have been created or that tests have passed.

### 3.7 `pyproject.toml` — project and tool configuration

This file is the standard place to declare project metadata and, depending on how it is configured, dependencies, packaging/build settings and development-tool settings.

It should be treated as the source of truth for the project's declared requirements. The installed-package list shown by pip includes both direct requirements and packages installed as dependencies of other packages, so it should not be copied wholesale into the direct requirements list.

The exact contents of `pyproject.toml` have not yet been reviewed in the information available for this README. Review it before changing or adding dependency declarations.

## 4. Requirements and installed packages

### 4.1 Environment requirements

The observed environment is a Windows machine using CMD and a Python virtual environment. The bytecode filenames in the captured environment indicate CPython 3.13; verify the active interpreter on the machine with:

```cmd
python --version
python -c "import sys; print(sys.executable)"
```

The second command should point to this project's `.venv\Scripts\python.exe`.

The project is already installed in editable mode. If setup must be reproduced, first inspect `pyproject.toml`, then install from the project root using the project's intended installation procedure. A common editable-install command is:

```cmd
python -m pip install -e .
```

Do not run a new installation or upgrade unnecessarily when the environment is already working.

### 4.2 Installed packages observed during setup

The following versions appeared in the shared output from `python -m pip list`. They describe the environment at the time of that check; they are **not all necessarily direct dependencies** declared by this project.

| Package | Version observed | Role |
|---|---:|---|
| `demand-agent-ingestion` | `0.1.0` | The local project, installed in editable mode. |
| `httpx` | `0.28.1` | HTTP client suitable for calling external APIs. |
| `pydantic` | `2.14.1` | Data parsing and validation support. |
| `pydantic-settings` | `2.16.2` | Application settings management. |
| `pymongo` | `4.19.0` | MongoDB client for Python. |
| `python-dotenv` | `1.2.4` | Loads environment values from `.env` files when configured to do so. |
| `tenacity` | `9.2.1` | Retry-policy support. |
| `pytest` | `9.2.0` | Test runner. |
| `pytest-cov` | `7.1.0` | Coverage reporting integration for pytest. |
| `coverage` | `7.17.0` | Code coverage measurement. |
| `ruff` | `0.17.3` | Python linting and code-quality checks. |
| `pip` | `26.2.2` | Python package installer. |

Supporting packages also observed include `annotated-types`, `anyio`, `certifi`, `colorama`, `dnspython`, `h11`, `httpcore`, `idna`, `iniconfig`, `packaging`, `pluggy`, `Pygments`, `pydantic_core`, `typing_extensions` and `typing-inspection`. These support other packages or developer tooling and generally do not need to be added as direct project requirements unless the source code imports them directly.

### 4.3 Which packages are likely to be used by the module?

For the planned functionality, the roles are likely to be:

- `httpx` for making weather API requests.
- `pydantic-settings` (with `pydantic`) for application configuration and validation.
- `pymongo` for MongoDB access.
- `python-dotenv` for `.env` loading, if that is how settings are configured.
- `tenacity` for retries, if the adapter uses it.
- `pytest`, `pytest-cov` and `ruff` for testing, coverage and code quality.

Confirm each package against `pyproject.toml` and actual imports. Do not assume that a package is required at runtime merely because it is installed.

### 4.4 Environment variables and secrets

Settings such as the application environment, MongoDB database name, HTTP timeout and retry configuration were being inspected through `get_settings()`.

The exact variable names, defaults and required values should be taken from the actual configuration implementation and `pyproject.toml`/documentation. Do not put real passwords, connection strings, tokens or other secrets in this README or commit them to version control. If `.env` is used, keep it private and consider providing a `.env.example` with placeholder values only.

## 5. Useful Windows CMD commands

Run these from the project root unless a command says otherwise.

### Activate the virtual environment

```cmd
.venv\Scripts\activate.bat
```

### Show Python version and active interpreter

```cmd
python --version
python -c "import sys; print(sys.executable)"
```

### List installed packages

```cmd
python -m pip list
```

### Export installed package/version pairs for inspection

```cmd
python -m pip freeze
```

This reports the full installed environment, including transitive dependencies. It should not automatically replace the project's curated dependency declarations.

### Check package dependency consistency

```cmd
python -m pip check
```

The observed result was `No broken requirements found.`

### Display the project configuration

```cmd
type pyproject.toml
```

### Show folders only

```cmd
tree /A
```

### Show folders and files

```cmd
tree /F /A
```

### Run tests (when test cases exist)

```cmd
python -m pytest -v
```

### Run Ruff (if the project has Ruff configuration or compatible defaults)

```cmd
python -m ruff check .
```

## 6. Data and reliability considerations

When the weather adapter is implemented, it should handle common ingestion concerns:

- **Timeouts:** a remote request should not wait indefinitely.
- **Retries:** retry only suitable transient failures, with sensible limits.
- **Validation:** reject or flag records with missing or invalid required fields.
- **Timestamps and units:** make the time zone, timestamp format and measurement units explicit.
- **Duplicate data:** decide how repeated observations should be identified and handled.
- **Logging:** report useful errors without exposing secrets.
- **Database errors:** distinguish a valid API response from a successful database write.
- **Tests:** test normal responses and failure conditions separately.

These are implementation recommendations for a robust ingestion pipeline, not assertions that all are already present in the code.

## 7. Suggested next steps

1. Review `pyproject.toml` to confirm the declared runtime and development dependencies.
2. Inspect the actual files with `tree /F /A` and document each existing Python module accurately.
3. Review the settings implementation and record the setting names, defaults and required environment variables.
4. Implement and test the weather adapter, including timeout and error handling.
5. Define the normalized weather record schema and validation rules.
6. Implement or verify the MongoDB storage component and test its behaviour.
7. Add automated tests for configuration, API response handling, validation and storage.
8. Add a DAG or other scheduled runner only after deciding which workflow orchestration tool the project will use.
9. Test the complete flow from API retrieval to validated storage before calling the ingestion pipeline operational.

## 8. Current health summary

- **Virtual environment:** created and activated during setup.
- **Project package:** recognized as `demand-agent-ingestion` `0.1.0` in editable mode.
- **Dependency consistency:** `pip check` reported no broken requirements.
- **Invalid `~ip` distribution warning:** investigated and resolved according to the user's confirmation.
- **Configuration loader:** import/call of `get_settings()` was part of the setup checks.
- **End-to-end data ingestion:** not yet confirmed by the available evidence.

---

*Keep this README updated as actual source files, tests and integrations are implemented. Update the status section only when supported by command output or test results.*
