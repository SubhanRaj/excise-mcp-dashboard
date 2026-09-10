<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="noindex, nofollow">
    <title>@yield('code') — {{ config('app.name') }}</title>
    {{-- Standalone placeholder. The Milestone 5 design-system pass replaces this
         with the sibling apps' <x-error-page> component and the branded layout. --}}
    <style>
        :root { color-scheme: light dark; }
        body {
            margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
            font: 15px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
            background: #f7f7f8; color: #1a1a1a; padding: 24px;
        }
        .box { max-width: 30rem; text-align: center; }
        .code { font-size: 3rem; font-weight: 700; color: #4a2bc2; letter-spacing: -0.02em; }
        .msg { margin-top: .5rem; font-size: 1.05rem; }
        .hint { margin-top: 1.25rem; font-size: .9rem; opacity: .7; }
        a { color: #4a2bc2; }
        @media (prefers-color-scheme: dark) {
            body { background: #131316; color: #ececec; }
            .code, a { color: #b3a1f5; }
        }
    </style>
</head>
<body>
    <div class="box">
        <div class="code">@yield('code')</div>
        <p class="msg">@yield('message')</p>
        <p class="hint">@yield('hint', 'If this keeps happening, tell the system administrator.')</p>
    </div>
</body>
</html>
