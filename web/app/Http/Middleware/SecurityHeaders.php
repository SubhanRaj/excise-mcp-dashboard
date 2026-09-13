<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class SecurityHeaders
{
    public function handle(Request $request, Closure $next): Response
    {
        $response = $next($request);

        // Prevent clickjacking — disallow embedding this app in any frame
        $response->headers->set('X-Frame-Options', 'SAMEORIGIN');

        // Prevent MIME sniffing — browser must honour the declared Content-Type
        $response->headers->set('X-Content-Type-Options', 'nosniff');

        // Limit referrer leakage — only origin is sent on cross-origin requests
        $response->headers->set('Referrer-Policy', 'strict-origin-when-cross-origin');

        // Disable browser APIs unused by this application
        $response->headers->set('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=(), usb=()');

        // This app defines no public route (web/plan/webui.md §3) — every page is internal
        // staff tooling, so noindex applies site-wide rather than scoped to an admin prefix.
        $response->headers->set('X-Robots-Tag', 'noindex, nofollow, noarchive');

        // Content Security Policy. unsafe-inline covers the inline <script> blocks in the
        // Blade shell (theme anti-flash, Alpine directives); unsafe-eval covers Alpine.js
        // (bundled in Livewire 4), which evaluates x-data/x-init via `new Function()`.
        // Sources are locked to self plus jsDelivr (Plotly, Chart.js, Cleave.js, marked +
        // a highlighter, Dexie) and Google Fonts — no orchestrator origin, since web/ calls
        // it server-side only and the browser never reaches it directly.
        $csp = implode('; ', [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data:",
            "connect-src 'self'",
            "frame-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]);
        $response->headers->set('Content-Security-Policy', $csp);

        // HSTS — only sent over HTTPS to avoid breaking HTTP-only local dev
        if ($request->isSecure()) {
            $response->headers->set(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains'
            );
        }

        return $response;
    }
}
