"""
Lambda entrypoint wrapper.

Lambda calls `<module>.<function>`; this file exposes `handler` and reuses
the project's existing `main()` orchestration.
"""

from aum_report_pipeline.main import main


def handler(event, context):
    # event/context are unused because this pipeline generates reports for default windows.
    main()
    return {
        "statusCode": 200,
        "body": "AUM report pipeline executed successfully",
    }

