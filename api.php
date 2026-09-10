<?php
/**
 * 多智能体流水线 - API
 * 提供:作品列表/详情/脚本源码/图片代理/流程说明
 * 所有数据从 data/ 目录读,只读 API。
 */
declare(strict_types=1);

error_reporting(E_ALL & ~E_DEPRECATED & ~E_NOTICE);
header('X-Content-Type-Options: nosniff');

// 兼容性:PHP < 7.4 没有 str_contains
if (!function_exists('str_contains')) {
    function str_contains(string $haystack, string $needle): bool {
        return $needle !== '' && strpos($haystack, $needle) !== false;
    }
}

define('PLAN_DIR', __DIR__);
define('DATA_DIR', PLAN_DIR . '/data');
define('PRODUCED_PATH', DATA_DIR . '/produced.json');
define('COLLECTED_PATH', DATA_DIR . '/collected.json');
define('JUDGED_PATH', DATA_DIR . '/judged.json');

$action = $_GET['action'] ?? '';
$id = $_GET['id'] ?? '';
$name = $_GET['name'] ?? '';
$path = $_GET['path'] ?? '';

// 安全白名单:脚本只允许看这几个
$ALLOWED_SCRIPTS = [
    'expand_keywords.py' => PLAN_DIR . '/expand_keywords.py',
    'scrape_xhs.py'      => PLAN_DIR . '/scrape_xhs.py',
    'judge.py'           => PLAN_DIR . '/judge.py',
    'execute.py'         => PLAN_DIR . '/execute.py',
    'collect_config.yaml'=> PLAN_DIR . '/collect_config.yaml',
];

// ============ 路由 ============
switch ($action) {
    case 'list':   echo_json(list_posts()); break;
    case 'post':   echo_json(get_post($id)); break;
    case 'scripts':echo_json(list_scripts($ALLOWED_SCRIPTS)); break;
    case 'script':echo_json(get_script($name, $ALLOWED_SCRIPTS)); break;
    case 'flow':   echo_json(get_flow()); break;
    case 'image': serve_image($path); break;
    case 'md_download': serve_md($id); break;
    case 'stats':  echo_json(get_stats()); break;
    default:
        http_response_code(400);
        echo_json(['error' => 'unknown action', 'available' => [
            'list','post','scripts','script','flow','image','md_download','stats'
        ]]);
}

// ============ 业务函数 ============

function list_posts(): array {
    $data = load_json(PRODUCED_PATH);
    $posts = [];
    foreach ($data['posts'] ?? [] as $p) {
        $paths = $p['image_paths'] ?? [];
        $posts[] = [
            'topic_id' => $p['topic_id'] ?? '',
            'track'    => $p['track'] ?? '',
            'title'    => $p['title'] ?? '',
            'tags'     => $p['tags'] ?? [],
            'image_count' => count($paths),
            'cover_url' => $paths ? ('api.php?action=image&path=' . urlencode($paths[0])) : '',
            'has_md'   => isset($p['md_file']),
            'has_skill_script' => isset($p['skill_script_path']),
            'body_len' => mb_strlen($p['body'] ?? ''),
            'status'   => $p['status'] ?? '',
        ];
    }
    return ['total' => count($posts), 'posts' => $posts];
}

function get_post(string $id): array {
    $data = load_json(PRODUCED_PATH);
    foreach ($data['posts'] ?? [] as $p) {
        if (($p['topic_id'] ?? '') === $id) {
            // 图片路径转 API URL
            $p['image_urls'] = array_map(function($p) {
                return 'api.php?action=image&path=' . urlencode($p);
            }, $p['image_paths'] ?? []);
            // skill script 内容
            if (isset($p['skill_script_path']) && is_file($p['skill_script_path'])) {
                $p['skill_script_content'] = file_get_contents($p['skill_script_path']);
            }
            // markdown 模板内容 + 下载链接
            if (isset($p['md_file'])) {
                if (is_file($p['md_file'])) {
                    $p['md_content'] = file_get_contents($p['md_file']);
                }
                $p['md_name'] = basename($p['md_file']);
                $p['md_download_url'] = 'api.php?action=md_download&id=' . urlencode($id);
            }
            return ['post' => $p];
        }
    }
    http_response_code(404);
    return ['error' => 'post not found', 'id' => $id];
}

function list_scripts(array $allowed): array {
    $scripts = [];
    foreach ($allowed as $name => $path) {
        $scripts[] = [
            'name' => $name,
            'size' => is_file($path) ? filesize($path) : 0,
            'mtime' => is_file($path) ? filemtime($path) : 0,
        ];
    }
    return ['scripts' => $scripts];
}

function get_script(string $name, array $allowed): array {
    if (!isset($allowed[$name])) {
        http_response_code(404);
        return ['error' => 'script not allowed or not found', 'name' => $name];
    }
    $path = $allowed[$name];
    if (!is_file($path)) {
        http_response_code(404);
        return ['error' => 'file not exists', 'name' => $name];
    }
    $content = file_get_contents($path);
    return [
        'name' => $name,
        'content' => $content,
        'size' => strlen($content),
    ];
}

function get_flow(): array {
    // 流程图说明:01 -> 02 -> 03
    $collected = load_json(COLLECTED_PATH);
    $judged = load_json(JUDGED_PATH);
    $produced = load_json(PRODUCED_PATH);
    $total_samples = 0;
    $total_keywords = 0;
    foreach ($collected['tracks'] ?? [] as $t) {
        $total_samples += count($t['samples'] ?? []);
        $total_keywords += count($t['keywords'] ?? []);
    }
    $total_topics = 0;
    $total_cards = 0;
    foreach ($judged['tracks'] ?? [] as $t) {
        $total_topics += count($t['topics'] ?? []);
        $total_cards += count($t['keyword_cards'] ?? []);
    }
    return [
        'steps' => [
            [
                'id' => '01',
                'name' => '收集智能体 Collector',
                'script' => 'expand_keywords.py + scrape_xhs.py',
                'config' => 'collect_config.yaml',
                'input'  => '种子关键词(三轨)',
                'output' => 'collected.json',
                'stats' => [
                    'keywords' => $total_keywords,
                    'samples' => $total_samples,
                ],
                'purpose' => '关键词 LLM 扩展 + 小红书搜索结果抓取,带登录态保存',
            ],
            [
                'id' => '02',
                'name' => '判断智能体 Judge',
                'script' => 'judge.py',
                'input'  => 'collected.json',
                'output' => 'judged.json',
                'stats' => [
                    'keyword_cards' => $total_cards,
                    'topics' => $total_topics,
                ],
                'purpose' => '关键词评分(热度/竞争/趋势/反馈/契合度)+ LLM 爆款模式提炼 + 选题生成',
            ],
            [
                'id' => '03',
                'name' => '执行智能体 Executor',
                'script' => 'execute.py',
                'input'  => 'judged.json',
                'output' => 'produced.json',
                'stats' => [
                    'posts' => count($produced['posts'] ?? []),
                ],
                'purpose' => '三轨分派子流程:教程出步骤+配图,Skill 出代码+演示,PPT 轨出纯 Markdown 完整逐页文案模板+封面图(内容为王)',
            ],
        ],
        'feedback_loop' => '发布效果回流到 feedback.json,01/02 下轮据此加权或拉黑关键词',
    ];
}

function get_stats(): array {
    $data = load_json(PRODUCED_PATH);
    $stats = ['total' => 0, 'by_track' => [], 'total_images' => 0, 'total_md' => 0];
    foreach ($data['posts'] ?? [] as $p) {
        $stats['total']++;
        $t = $p['track'] ?? 'unknown';
        $stats['by_track'][$t] = ($stats['by_track'][$t] ?? 0) + 1;
        $stats['total_images'] += count($p['image_paths'] ?? []);
        if (isset($p['md_file'])) $stats['total_md']++;
    }
    return $stats;
}

function serve_image(string $path) {
    // 只允许 data/images 下的图片
    $real = realpath($path);
    $images_root = realpath(DATA_DIR . '/images');
    $ppt_root = realpath(DATA_DIR . '/ppt_templates');
    if (!$real || !$images_root || !str_starts_with_safe($real, $images_root) &&
        !($ppt_root && str_starts_with_safe($real, $ppt_root))) {
        http_response_code(403);
        echo 'forbidden path';
        return;
    }
    if (!is_file($real)) {
        http_response_code(404);
        echo 'image not found';
        return;
    }
    $ext = strtolower(pathinfo($real, PATHINFO_EXTENSION));
    $types = ['png' => 'image/png', 'jpg' => 'image/jpeg', 'jpeg' => 'image/jpeg', 'gif' => 'image/gif'];
    if (!isset($types[$ext])) {
        http_response_code(400);
        echo 'bad type';
        return;
    }
    header('Content-Type: ' . $types[$ext]);
    header('Content-Length: ' . filesize($real));
    header('Cache-Control: public, max-age=86400');
    readfile($real);
}

function serve_md(string $id) {
    $data = load_json(PRODUCED_PATH);
    $ppt_root = realpath(DATA_DIR . '/ppt_templates');
    foreach ($data['posts'] ?? [] as $p) {
        if (($p['topic_id'] ?? '') === $id && isset($p['md_file'])) {
            $f = $p['md_file'];
            $real = realpath($f);
            // 白名单:必须在 data/ppt_templates 下,且扩展名为 .md
            if (!$real || !$ppt_root || !str_starts_with_safe($real, $ppt_root)
                || strtolower(pathinfo($real, PATHINFO_EXTENSION)) !== 'md'
                || !is_file($real)) {
                http_response_code(403);
                echo 'invalid md path';
                return;
            }
            $name = basename($real);
            header('Content-Type: text/markdown; charset=utf-8');
            header('Content-Disposition: attachment; filename="' . $name . '"');
            header('Content-Length: ' . filesize($real));
            readfile($real);
            return;
        }
    }
    http_response_code(404);
    echo 'md not found for id ' . $id;
}

// ============ 工具 ============

function load_json(string $path): array {
    if (!is_file($path)) return [];
    $s = file_get_contents($path);
    $d = json_decode($s, true);
    return is_array($d) ? $d : [];
}

function echo_json($data) {
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
}

function str_starts_with_safe(string $haystack, string $needle): bool {
    return $needle !== '' && substr($haystack, 0, strlen($needle)) === $needle;
}
