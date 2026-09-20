<?php

namespace App\Http\Controllers;

use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * The customization panel's save endpoint (resources/views/components/customization-panel
 * .blade.php): a plain fetch() write of client-held state, not a page render, so a plain
 * route fits the same way Ask's stage-polling route does.
 */
class UiPreferencesController extends Controller
{
    public function update(Request $request): JsonResponse
    {
        $prefs = $request->validate([
            'theme' => ['required', 'in:light,dark,system'],
            'font' => ['required', 'in:inter,noto-sans,merriweather,space-grotesk,jetbrains-mono'],
            'text_size' => ['required', 'integer', 'between:0,4'],
            'line_spacing' => ['required', 'in:compact,normal,relaxed'],
            'content_width' => ['required', 'in:normal,wide,full'],
            'table_density' => ['required', 'in:comfortable,compact'],
            'accent' => ['required', 'in:violet,saffron'],
            'high_contrast' => ['required', 'boolean'],
            'reduce_motion' => ['required', 'boolean'],
        ]);

        $request->user()->update(['ui_prefs' => $prefs]);

        return response()->json(['status' => 'ok']);
    }
}
