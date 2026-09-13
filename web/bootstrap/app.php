<?php

use App\Http\Middleware\HasPrivilege;
use App\Http\Middleware\IsAdmin;
use App\Http\Middleware\LogMutation;
use App\Http\Middleware\SecurityHeaders;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Http\Request;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        commands: __DIR__.'/../routes/console.php',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        // Cloudflare terminates TLS at its edge and cloudflared forwards to this app over
        // plain HTTP on loopback — trust only that hop's X-Forwarded-* headers so
        // url()/redirect()/signed-URL validation know the original request was HTTPS.
        $middleware->trustProxies(at: ['127.0.0.1']);

        $middleware->append(LogMutation::class);
        $middleware->append(SecurityHeaders::class);

        $middleware->redirectGuestsTo(fn () => route('login'));
        $middleware->redirectUsersTo(fn () => route('ask'));

        $middleware->alias([
            'is_admin' => IsAdmin::class,
            'privilege' => HasPrivilege::class,
        ]);
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        $exceptions->shouldRenderJsonWhen(
            fn (Request $request) => $request->is('api/*') || $request->expectsJson(),
        );
    })->create();
