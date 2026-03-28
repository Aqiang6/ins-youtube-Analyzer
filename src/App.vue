<template>
  <div class="main-container">
    <div class="card">
      <h1>高清下载器</h1>
      <div class="input-box">
        <input 
          ref="inputRef"
          v-model="inputUrl" 
          placeholder="粘贴链接..." 
          :disabled="loading" 
          @keyup.enter="handleAnalyze"
        />
        <button @click="handleAnalyze" :disabled="loading">
          {{ loading ? '解析中...' : '解析' }}
        </button>
      </div>

      <div v-if="loading" class="progress-container">
        <p class="status-text">{{ statusText }}</p>
        <div class="progress-bar">
          <div class="fill" :style="{ width: progress + '%' }"></div>
        </div>
      </div>

      <div v-if="videoInfo" class="result-card">
        <img :src="videoInfo.thumbnail" class="cover" />
        <div class="details">
          <h3>{{ videoInfo.title }}</h3>
          <p v-if="videoInfo.duration">
            时长: {{ Math.floor(videoInfo.duration / 60) }}分{{ videoInfo.duration % 60 }}秒
          </p>
          <div class="quality-list">
            <button 
              v-for="opt in videoInfo.options" 
              :key="opt.id"
              @click="processDownload(opt)"
              class="quality-btn"
              :disabled="downloading"
            >
              {{ opt.height }}p 
              <span v-if="opt.needsMerge" class="badge">高清合并</span>
              <span v-else class="badge direct">直接下载</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';

const inputUrl = ref('');
const videoInfo = ref(null);
const loading = ref(false);
const downloading = ref(false);
const progress = ref(0);
const statusText = ref('');
const inputRef = ref(null);

// API 基础地址
const API_BASE = 'http://localhost:8000';

// 辅助函数：安全获取输入框的值
const getInputValue = () => {
  // 直接获取 inputRef 的 DOM 元素的值，避免响应式对象的问题
  if (inputRef.value) {
    const domValue = inputRef.value.value;
    if (domValue && typeof domValue === 'string') {
      return domValue.trim();
    }
  }
  
  // 降级方案：从 ref 中获取
  let val = inputUrl.value;
  
  // 如果 val 是 ref 对象，获取其内部值
  if (val && typeof val === 'object' && 'value' in val) {
    val = val.value;
  }
  
  // 确保是字符串
  if (val && typeof val === 'string') {
    return val.trim();
  }
  
  return '';
};

// 1. 调用后端接口获取画质列表
const handleAnalyze = async () => {
  // 使用辅助函数获取输入值
  const trimmedUrl = getInputValue();
  
  if (!trimmedUrl) {
    alert('请输入 Instagram 链接');
    console.log('输入值为空');
    return;
  }
  
  // 同步更新 inputUrl ref 的值
  inputUrl.value = trimmedUrl;
  
  loading.value = true;
  progress.value = 0;
  statusText.value = '正在解析视频信息...';
  
  try {
    const res = await fetch(
      `${API_BASE}/analyze?url=${encodeURIComponent(trimmedUrl)}`
    );
    
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `解析失败 (${res.status})`);
    }
    
    videoInfo.value = await res.json();
    statusText.value = '解析成功，请选择画质';
    progress.value = 100;
    
    // 3秒后隐藏进度条
    setTimeout(() => {
      if (statusText.value === '解析成功，请选择画质') {
        statusText.value = '';
        progress.value = 0;
      }
    }, 3000);
    
  } catch (e) {
    console.error('解析错误:', e);
    alert('解析失败: ' + e.message);
    statusText.value = '';
    progress.value = 0;
  } finally {
    loading.value = false;
  }
};

// 2. 处理下载逻辑
const processDownload = async (option) => {
  if (downloading.value) {
    alert('正在下载中，请稍后...');
    return;
  }
  
  if (!videoInfo.value) {
    alert('视频信息不存在，请重新解析');
    return;
  }
  
  downloading.value = true;
  progress.value = 0;
  
  try {
    // 如果需要合并，使用合并接口
    if (option.needsMerge) {
      if (!videoInfo.value.audioUrl) {
        throw new Error('未找到音频轨道，无法合并');
      }
      
      statusText.value = '正在下载并合并音视频...';
      progress.value = 10;
      
      // 使用后端合并接口
      const params = new URLSearchParams({
        video_url: option.url,
        audio_url: videoInfo.value.audioUrl,
        title: videoInfo.value.title,
        height: option.height
      });
      
      const downloadUrl = `${API_BASE}/download?${params.toString()}`;
      
      // 创建一个隐藏的 a 标签来触发下载
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `${videoInfo.value.title}_${option.height}p.mp4`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      
      statusText.value = '下载已开始，请稍后...';
      
    } else {
      // 直接下载（不需要合并）
      statusText.value = '正在下载...';
      progress.value = 30;
      
      const params = new URLSearchParams({
        url: option.url,
        title: `${videoInfo.value.title}_${option.height}p`
      });
      
      const downloadUrl = `${API_BASE}/download_direct?${params.toString()}`;
      
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `${videoInfo.value.title}_${option.height}p.${option.ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      
      statusText.value = '下载已开始';
    }
    
    // 下载完成后立即将进度设为100并清除状态
    progress.value = 100;
    
    // 3秒后重置状态
    setTimeout(() => {
      if (statusText.value === '下载已开始' || statusText.value === '下载已开始，请稍后...') {
        statusText.value = '';
        progress.value = 0;
      }
    }, 3000);
    
  } catch (e) {
    console.error('下载错误:', e);
    alert('下载失败: ' + e.message);
    statusText.value = '';
    progress.value = 0;
  } finally {
    downloading.value = false;
  }
};
</script>

<style scoped>
.main-container { 
  padding: 30px; 
  max-width: 600px; 
  margin: auto; 
  font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}

.card { 
  border: 1px solid #dbdbdb; 
  border-radius: 12px; 
  padding: 24px; 
  background: white;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

h1 {
  font-size: 1.5rem;
  margin-bottom: 20px;
  color: #262626;
  text-align: center;
}

.input-box { 
  display: flex; 
  gap: 10px; 
  margin-bottom: 20px; 
}

input { 
  flex: 1; 
  padding: 12px; 
  border: 1px solid #dbdbdb; 
  border-radius: 8px; 
  font-size: 14px;
  transition: border-color 0.2s;
}

input:focus {
  outline: none;
  border-color: #0095f6;
}

button {
  background: #0095f6;
  color: white;
  border: none;
  padding: 0 24px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
  font-size: 14px;
}

button:hover:not(:disabled) {
  background: #1877f2;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.quality-list { 
  display: flex; 
  flex-wrap: wrap; 
  gap: 10px; 
  margin-top: 15px; 
}

.quality-btn { 
  background: #efefef;
  color: #262626;
  border: none;
  padding: 10px 18px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.quality-btn:hover:not(:disabled) {
  background: #e4e4e4;
}

.quality-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #0095f6;
  color: white;
}

.badge.direct {
  background: #8e8e8e;
}

.result-card { 
  display: flex; 
  gap: 20px; 
  margin-top: 24px; 
  border-top: 1px solid #efefef; 
  padding-top: 20px; 
}

.cover { 
  width: 120px; 
  border-radius: 8px; 
  object-fit: cover;
}

.details {
  flex: 1;
}

.details h3 {
  margin: 0 0 5px 0;
  font-size: 16px;
  color: #262626;
  word-break: break-word;
}

.details p {
  margin: 0 0 10px 0;
  font-size: 13px;
  color: #8e8e8e;
}

.progress-container {
  margin: 15px 0;
}

.status-text {
  font-size: 13px;
  color: #262626;
  margin-bottom: 8px;
  text-align: center;
}

.progress-bar { 
  height: 4px; 
  background: #efefef; 
  border-radius: 2px; 
  overflow: hidden; 
}

.fill { 
  height: 100%; 
  background: #0095f6; 
  transition: width 0.3s ease;
  border-radius: 2px;
}

@media (max-width: 500px) {
  .main-container {
    padding: 15px;
  }
  
  .result-card {
    flex-direction: column;
  }
  
  .cover {
    width: 100%;
    max-height: 200px;
    object-fit: cover;
  }
  
  .quality-btn {
    flex: 1;
    justify-content: center;
  }
}
</style>