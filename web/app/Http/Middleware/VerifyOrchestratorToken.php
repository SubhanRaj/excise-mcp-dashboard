<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Gates routes/api.php — the one inbound direction the orchestrator calls into web/
 * (GET /api/schema-notes), reusing the same shared bearer token web/'s own
 * OrchestratorClient already sends the other way (config('services.orchestrator.token'),
 * ORCH_BEARER_TOKEN in orchestrator/.env).
 */
class VerifyOrchestratorToken
{
    /**
     * @param  Closure(Request): (Response)  $next
     */
    public function handle(Request $request, Closure $next): Response
    {
        $token = $request->bearerToken();

        // A blank request token must never match a misconfigured, blank config token —
        // require an actual non-empty value on both sides before comparing them.
        abort_unless(
            is_string($token) && $token !== '' && hash_equals((string) config('services.orchestrator.token'), $token),
            401
        );

        return $next($request);
    }
}
