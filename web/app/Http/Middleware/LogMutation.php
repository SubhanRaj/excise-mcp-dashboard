<?php

namespace App\Http\Middleware;

use App\Models\ActivityLog;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class LogMutation
{
    /**
     * Route names excluded because they'd otherwise duplicate the dedicated login/logout
     * activity-log entries fired from AppServiceProvider's Login/Logout event listeners.
     *
     * 'livewire.update' is excluded because it's Livewire's one shared transport route for
     * every component interaction — clicks, model updates, and wire:poll ticks alike — so
     * logging it here would produce one row per poll tick that says nothing about what
     * actually happened. A Livewire action worth auditing calls ActivityLog::record() itself
     * with a real action name, the same way a controller does.
     */
    private const SKIP_ROUTES = [
        'otp.verify',
        'otp.resend',
        'login.attempt',
        'logout',
        'livewire.update',
    ];

    /**
     * @param  Closure(Request): (Response)  $next
     */
    public function handle(Request $request, Closure $next): Response
    {
        $response = $next($request);

        if (
            $request->user()
            && ! $request->isMethod('GET')
            && ! $request->isMethod('HEAD')
            && ! $request->isMethod('OPTIONS')
            && ! in_array($request->route()?->getName(), self::SKIP_ROUTES, true)
        ) {
            $action = $request->route()?->getName() ?? ($request->method().':'.$request->path());
            ActivityLog::record($action, $request, ['status' => $response->getStatusCode()]);
        }

        return $response;
    }
}
