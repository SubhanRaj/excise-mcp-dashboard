<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

#[Fillable(['user_id', 'action', 'ip_address', 'user_agent', 'metadata'])]
class ActivityLog extends Model
{
    public $timestamps = false;

    protected function casts(): array
    {
        return [
            'metadata' => 'array',
            'created_at' => 'datetime',
        ];
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    /**
     * Never throws — a logging failure must never break the request it's logging.
     */
    public static function record(string $action, Request $request, array $meta = [], ?int $userId = null): void
    {
        try {
            static::create([
                'user_id' => $userId ?? $request->user()?->id,
                'action' => $action,
                'ip_address' => $request->ip(),
                'user_agent' => substr((string) $request->userAgent(), 0, 500),
                'metadata' => array_merge([
                    'method' => $request->method(),
                    'url' => $request->fullUrl(),
                ], $meta),
                'created_at' => now(),
            ]);
        } catch (\Throwable $e) {
            Log::warning('ActivityLog::record failed', ['action' => $action, 'error' => $e->getMessage()]);
        }
    }
}
