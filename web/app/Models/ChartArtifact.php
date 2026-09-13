<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\MorphTo;
use Illuminate\Database\Eloquent\SoftDeletes;

#[Fillable(['owner_type', 'owner_id', 'spec', 'png_path', 'svg_path', 'pdf_path'])]
class ChartArtifact extends Model
{
    use HasUlids, SoftDeletes;

    protected function casts(): array
    {
        return [
            'spec' => 'array',
        ];
    }

    public function owner(): MorphTo
    {
        return $this->morphTo();
    }
}
