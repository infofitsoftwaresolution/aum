"""
AUM Report Pipeline — Demo Package

This package is only active when DEMO_MODE=true is set as an environment variable.
It provides synthetic sample data that exactly mimics the PostgreSQL query output,
allowing the full pipeline (report generation, S3 upload, cleanup) to run without
any database connection.

IMPORTANT: Nothing in this package is imported during normal production runs.
"""
