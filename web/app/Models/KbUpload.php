<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\SoftDeletes;

#[Fillable(['uploaded_by', 'original_name', 'title', 'status', 'origin_ref'])]
class KbUpload extends Model
{
    use HasUlids, SoftDeletes;

    public const STATUS_PENDING = 'pending';

    public const STATUS_WITHDRAWN = 'withdrawn';

    public function uploader(): BelongsTo
    {
        return $this->belongsTo(User::class, 'uploaded_by');
    }
}
