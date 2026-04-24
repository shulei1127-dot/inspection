from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()


@router.get("/", response_class=HTMLResponse, summary="Minimal homepage")
def get_homepage() -> HTMLResponse:
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>inspection-report-platform</title>
          <style>
            body {
              margin: 0;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
              background: #f5f7fb;
              color: #152033;
            }
            main {
              max-width: 760px;
              margin: 64px auto;
              padding: 0 20px;
            }
            section {
              background: #ffffff;
              border: 1px solid #d7dfeb;
              border-radius: 14px;
              padding: 28px;
              box-shadow: 0 10px 30px rgba(21, 32, 51, 0.06);
            }
            h1 {
              margin: 0 0 12px;
              font-size: 32px;
              line-height: 1.15;
            }
            p {
              margin: 0 0 18px;
              line-height: 1.6;
            }
            ul {
              margin: 0;
              padding-left: 20px;
            }
            li + li {
              margin-top: 10px;
            }
            a {
              color: #0b63ce;
              text-decoration: none;
            }
            a:hover {
              text-decoration: underline;
            }
            code {
              background: #eef3fb;
              padding: 2px 6px;
              border-radius: 6px;
            }
          </style>
        </head>
        <body>
          <main>
            <section>
              <h1>inspection-report-platform</h1>
              <p>
                A minimal MVP backend for uploaded inspection log packages, unified JSON generation,
                and DOCX report delivery.
              </p>
              <p>Useful entry points:</p>
              <ul>
                <li><a href="/docs">/docs</a> for interactive API testing</li>
                <li><a href="/console">/console</a> for the platform module dashboard</li>
                <li><a href="/xray">/xray</a> for the xray report generation workbench</li>
                <li><a href="/waf">/waf</a> for the minimal WAF log preprocessing workbench</li>
                <li><a href="/waf-audits/ui">/waf-audits/ui</a> for the WAF audit workbench</li>
                <li><a href="/health">/health</a> for service health</li>
                <li><a href="/api/tasks">/api/tasks</a> for task history</li>
                <li><a href="/openapi.json">/openapi.json</a> for the OpenAPI document</li>
              </ul>
              <p style="margin-top: 18px;">
                The main workflow starts from <code>POST /api/tasks</code>.
                The WAF preprocessing workflow starts from <code>POST /api/waf/preprocessing</code>.
              </p>
            </section>
          </main>
        </body>
        </html>
        """
    )
