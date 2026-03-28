from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import yt_dlp
import subprocess
import os
import uuid
import shutil
import requests
import threading
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建临时文件目录
TEMP_DIR = "temp_downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

# 尝试找到 FFmpeg 路径
def get_ffmpeg_path():
    """获取 FFmpeg 可执行文件路径"""
    # 首先检查是否在 PATH 中
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return ffmpeg_path
    
    # 常见的 FFmpeg 安装路径
    common_paths = [
        r'D:\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe',
        os.path.join(os.path.dirname(__file__), 'ffmpeg', 'ffmpeg.exe'),
        os.path.join(os.path.dirname(__file__), 'bin', 'ffmpeg.exe'),
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    return 'ffmpeg'  # 返回默认值，让系统尝试

FFMPEG_PATH = get_ffmpeg_path()

@app.get("/analyze")
async def analyze(url: str):
    """解析视频信息，获取可用的画质选项"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.instagram.com/',
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            
            video_options = []
            
            # 改进音频流获取：选择最佳音频流
            audio_url = None
            audio_formats = [f for f in formats if f.get('vcodec') == 'none']
            
            if audio_formats:
                # 优先选择高质量音频（高码率）
                best_audio = None
                best_bitrate = 0
                for audio_fmt in audio_formats:
                    bitrate = audio_fmt.get('tbr', 0) or audio_fmt.get('abr', 0)
                    ext = audio_fmt.get('ext', '')
                    # 优先 m4a 格式，然后 mp4
                    if ext in ['m4a', 'mp4'] and bitrate > best_bitrate:
                        best_bitrate = bitrate
                        best_audio = audio_fmt
                
                if best_audio:
                    audio_url = best_audio.get('url')
                elif audio_formats:
                    audio_url = audio_formats[0].get('url')

            # 提取所有分辨率并去重
            seen_heights = set()
            for f in formats:
                height = f.get('height')
                if height and height not in seen_heights and f.get('vcodec') != 'none':
                    # 如果 acodec 是 None，说明是 DASH 流（纯视频），需要合并音频
                    needs_merge = f.get('acodec') == 'none'
                    
                    video_options.append({
                        "id": f.get('format_id'),
                        "height": height,
                        "url": f.get('url'),
                        "needsMerge": needs_merge,
                        "ext": f.get('ext', 'mp4')
                    })
                    seen_heights.add(height)

            # 按分辨率从高到低排序
            video_options.sort(key=lambda x: x['height'], reverse=True)

            return {
                "title": sanitize_filename(info.get('title', 'Video')),
                "thumbnail": info.get('thumbnail'),
                "audioUrl": audio_url,
                "options": video_options,
                "duration": info.get('duration')
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/download")
async def download_video(video_url: str, audio_url: str = None, title: str = None, height: int = None):
    """
    下载并合并音视频
    """
    task_id = str(uuid.uuid4())[:8]
    temp_video = os.path.join(TEMP_DIR, f"{task_id}_video")
    temp_audio = os.path.join(TEMP_DIR, f"{task_id}_audio")
    output_file = os.path.join(TEMP_DIR, f"{task_id}_output.mp4")
    
    # 检测文件格式
    video_ext = 'mp4'
    audio_ext = 'mp3'
    
    try:
        # 如果没有提供音频 URL，直接下载视频
        if not audio_url:
            # 直接下载
            response = requests.get(video_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # 从 URL 或 content-type 判断格式
            content_type = response.headers.get('content-type', '')
            if 'webm' in content_type:
                video_ext = 'webm'
            elif 'mp4' in content_type:
                video_ext = 'mp4'
            
            temp_video_file = f"{temp_video}.{video_ext}"
            
            with open(temp_video_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            final_file = temp_video_file
        else:
            # 需要合并音频和视频
            # 下载视频 - 不预先指定扩展名
            response = requests.get(video_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # 判断视频格式
            content_type = response.headers.get('content-type', '')
            if 'webm' in content_type:
                video_ext = 'webm'
            else:
                video_ext = 'mp4'
            
            temp_video_file = f"{temp_video}.{video_ext}"
            with open(temp_video_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # 下载音频
            response = requests.get(audio_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # 判断音频格式
            content_type = response.headers.get('content-type', '')
            if 'm4a' in content_type or 'mp4' in content_type:
                audio_ext = 'm4a'
            elif 'webm' in content_type:
                audio_ext = 'webm'
            else:
                audio_ext = 'mp3'
            
            temp_audio_file = f"{temp_audio}.{audio_ext}"
            with open(temp_audio_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # 使用 FFmpeg 合并
            # 根据文件格式调整 FFmpeg 参数
            cmd = [
                FFMPEG_PATH, '-i', temp_video_file, '-i', temp_audio_file,
                '-c:v', 'copy',           # 视频直接复制
                '-c:a', 'aac',            # 音频编码为 AAC
                '-b:a', '128k',           # 音频码率
                '-map', '0:v:0',          # 选择第一个视频流
                '-map', '1:a:0',          # 选择第一个音频流
                '-movflags', '+faststart', # 优化网络播放
                '-y',                      # 覆盖输出文件
                output_file
            ]
            
            # 对于 webm 格式的视频，可能需要重新编码
            if video_ext == 'webm':
                cmd = [
                    FFMPEG_PATH, '-i', temp_video_file, '-i', temp_audio_file,
                    '-c:v', 'libx264',     # 重新编码为 H.264
                    '-c:a', 'aac',
                    '-b:v', '2000k',
                    '-b:a', '128k',
                    '-crf', '18',
                    '-movflags', '+faststart',
                    '-y',
                    output_file
                ]
            
            # 执行 FFmpeg 命令
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            if result.returncode != 0:
                print(f"FFmpeg 错误输出: {result.stderr}")
                raise Exception(f"FFmpeg 合并失败: {result.stderr}")
            
            final_file = output_file
            
            # 清理临时文件
            cleanup_files([temp_video_file, temp_audio_file])
        
        # 检查输出文件是否存在
        if not os.path.exists(final_file):
            raise Exception("输出文件不存在")
        
        # 构建文件名
        filename = f"{title}_{height}p.mp4" if height else f"{title}.mp4"
        filename = sanitize_filename(filename)
        
        # 返回文件
        return FileResponse(
            final_file,
            media_type="video/mp4",
            filename=filename
        )
        
    except Exception as e:
        print(f"下载错误: {e}")
        # 清理临时文件
        cleanup_files([temp_video, temp_audio, output_file])
        raise HTTPException(status_code=400, detail=f"下载失败: {str(e)}")
    finally:
        # 延迟清理输出文件
        def cleanup():
            time.sleep(10)
            cleanup_files([output_file])
        
        threading.Thread(target=cleanup).start()

@app.get("/download_direct")
async def download_direct(url: str, title: str = None):
    """直接下载（不需要合并的选项）"""
    task_id = str(uuid.uuid4())[:8]
    temp_file = os.path.join(TEMP_DIR, f"{task_id}_direct.mp4")
    
    try:
        # 下载文件
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with open(temp_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        filename = f"{title}.mp4" if title else "video.mp4"
        filename = sanitize_filename(filename)
        
        return FileResponse(
            temp_file,
            media_type="video/mp4",
            filename=filename
        )
        
    except Exception as e:
        cleanup_files([temp_file])
        raise HTTPException(status_code=400, detail=f"下载失败: {str(e)}")
    finally:
        def cleanup():
            time.sleep(5)
            cleanup_files([temp_file])
        
        threading.Thread(target=cleanup).start()

def cleanup_files(files):
    """清理临时文件"""
    for file in files:
        try:
            if file and os.path.exists(file):
                os.remove(file)
        except Exception:
            pass

def sanitize_filename(filename: str) -> str:
    """清理文件名中的非法字符"""
    # Windows 文件名非法字符
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    # 限制长度
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:190] + ext
    return filename

if __name__ == "__main__":
    import uvicorn
    print(f"FFmpeg 路径: {FFMPEG_PATH}")
    print(f"FFmpeg 存在: {os.path.exists(FFMPEG_PATH) if FFMPEG_PATH != 'ffmpeg' else '检查 PATH'}")
    uvicorn.run(app, host="0.0.0.0", port=8000)