<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>@yield('title', config('app.name'))</title></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;border:1px solid #e2e8f0;max-width:560px;width:100%;overflow:hidden;">
        <tr>
          <td style="background:#4a2bc2;padding:24px 32px;">
            <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:0.15em;text-transform:uppercase;color:#c0b3ff;">Government of Uttar Pradesh</p>
            <p style="margin:4px 0 0;font-size:18px;font-weight:600;color:#fff;">Department of Excise — MCP Dashboard</p>
          </td>
        </tr>
        <tr>
          <td style="padding:32px;">
            @yield('content')
          </td>
        </tr>
        <tr>
          <td style="padding:20px 32px;border-top:1px solid #e2e8f0;background:#f8fafc;">
            <p style="margin:0;font-size:12px;color:#94a3b8;">UP Excise MCP Dashboard &middot; Department of Excise, Government of Uttar Pradesh</p>
            <p style="margin:4px 0 0;font-size:11px;color:#cbd5e1;">Internal use only &middot; Unauthorized access is prohibited</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
