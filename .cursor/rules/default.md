# TikLocal - 本地媒体浏览器开发规则

这是一个基于Flask的本地媒体浏览器应用，提供类似TikTok的视频浏览体验和类似Pinterest的图片浏览体验。

## 项目架构与技术栈

### 后端技术栈
- **Flask**: 轻量级Python Web框架
- **Waitress**: 生产级WSGI服务器
- **Python 3.10+**: 主要开发语言

### 前端技术栈
- **Tailwind CSS v4**: 现代原子化CSS框架，提供响应式设计
- **原生JavaScript**: 保持轻量级，避免复杂依赖
- **Feather Icons**: 轻量级图标库
- **Hammer.js**: 触摸手势库，用于移动端交互

### 项目结构
```
tiklocal/
├── __init__.py          # 主Flask应用
├── templates/           # Jinja2模板文件
│   ├── base.html       # 基础模板
│   ├── tiktok.html     # TikTok样式视频浏览
│   ├── gallery.html    # Pinterest样式图片浏览
│   ├── browse.html     # 文件浏览器
│   └── ...
└── static/             # 静态资源
    ├── app.css         # 自定义样式和Tailwind配置
    ├── dark.css        # 暗色主题变量
    ├── tailwind.config.js # Tailwind配置文件
    └── *.js            # JavaScript文件
```

## 开发原则

### 1. 简洁性原则
- **最小化依赖**: 仅使用必需的库，避免过度工程化
- **单文件架构**: 主要逻辑集中在`__init__.py`中，保持代码紧凑
- **原子化CSS**: 使用Tailwind的utility-first方法，保持样式简洁

### 2. 稳定性原则
- **错误处理**: 所有文件操作都要有适当的错误处理
- **路径安全**: 使用`Path`对象处理文件路径，防止路径遍历攻击
- **类型检查**: 验证MIME类型确保媒体文件的有效性
- **优雅降级**: 确保在各种环境下都能正常运行

### 3. 性能优化
- **CSS优化**: 利用Tailwind CSS v4的新引擎实现更快的构建
- **延迟加载**: 图片和视频采用延迟加载策略
- **分页处理**: 大量文件使用分页避免内存溢出
- **缓存策略**: 适当使用浏览器缓存和服务器缓存

### 4. 用户体验原则
- **响应式设计**: 使用Tailwind的响应式工具类
- **触摸友好**: 移动端优先的交互设计
- **主题支持**: 使用CSS变量和Tailwind的暗色模式
- **快捷操作**: 提供收藏、删除等常用功能

## Tailwind CSS v4 开发指南

### 配置设置
```javascript
// tailwind.config.js
export default {
  content: ['./tiklocal/templates/**/*.html'],
  theme: {
    extend: {
      colors: {
        primary: 'rgb(var(--color-primary) / <alpha-value>)',
        secondary: 'rgb(var(--color-secondary) / <alpha-value>)',
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      }
    }
  },
  plugins: []
}
```

### CSS变量定义
```css
/* static/app.css */
:root {
  --color-primary: 59 130 246; /* blue-500 */
  --color-secondary: 16 185 129; /* emerald-500 */
  --spacing-safe-top: env(safe-area-inset-top);
  --spacing-safe-bottom: env(safe-area-inset-bottom);
}

[data-theme="dark"] {
  --color-primary: 96 165 250; /* blue-400 */
  --color-secondary: 52 211 153; /* emerald-400 */
}
```

## 代码风格指南

### Python代码规范
```python
# 使用类型提示
from pathlib import Path
from typing import List, Dict, Optional

# 函数命名使用snake_case
def get_media_files(directory: Path, media_type: str = 'video') -> List[Path]:
    """获取指定目录下的媒体文件"""
    pass

# 路由处理函数使用描述性后缀
@app.route('/gallery')
def gallery_view():
    pass

# 错误处理要具体
try:
    target.unlink()
except FileNotFoundError:
    flash('文件不存在')
except PermissionError:
    flash('没有删除权限')
```

### HTML模板规范
```html
<!-- 使用语义化的HTML标签配合Tailwind类 -->
<main class="container mx-auto px-4 py-8">
  <section class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
    <article class="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
      <!-- 内容 -->
    </article>
  </section>
</main>

<!-- 所有交互元素要有适当的ARIA标签和Tailwind样式 -->
<button class="inline-flex items-center px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/90 focus:ring-2 focus:ring-primary focus:ring-offset-2 transition-colors" 
        aria-label="播放视频">
  <i data-feather="play" class="w-4 h-4 mr-2"></i>
  播放
</button>
```

### Tailwind CSS样式规范
```css
/* 自定义组件样式 */
@layer components {
  .media-viewer {
    @apply fixed inset-0 z-50 bg-black flex items-center justify-center;
  }
  
  .media-grid {
    @apply grid gap-4;
    @apply grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4;
  }
  
  .btn-primary {
    @apply px-4 py-2 bg-primary text-white rounded-md;
    @apply hover:bg-primary/90 focus:ring-2 focus:ring-primary;
    @apply transition-all duration-200;
  }
}

/* 自定义工具类 */
@layer utilities {
  .safe-area-top {
    padding-top: var(--spacing-safe-top);
  }
  
  .safe-area-bottom {
    padding-bottom: var(--spacing-safe-bottom);
  }
}
```

### 响应式设计模式
```html
<!-- 移动端优先的响应式设计 -->
<div class="flex flex-col md:flex-row gap-4">
  <div class="w-full md:w-2/3">
    <!-- 主内容 -->
  </div>
  <div class="w-full md:w-1/3">
    <!-- 侧边栏 -->
  </div>
</div>

<!-- 网格布局响应式 -->
<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2 md:gap-4">
  <!-- 媒体项目 -->
</div>
```

## 主题和暗色模式

### 主题切换实现
```javascript
// 主题切换函数
function toggleTheme() {
  const html = document.documentElement;
  const currentTheme = html.getAttribute('data-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  
  html.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme);
}

// 初始化主题
function initTheme() {
  const savedTheme = localStorage.getItem('theme') || 
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', savedTheme);
}
```

### 暗色模式样式
```html
<!-- 使用Tailwind的dark:修饰符 -->
<div class="bg-white dark:bg-gray-900 text-gray-900 dark:text-white">
  <h1 class="text-2xl font-bold text-gray-900 dark:text-white">标题</h1>
  <p class="text-gray-600 dark:text-gray-300">内容文本</p>
</div>
```

## 新功能开发指南

### 添加新路由
1. 在`__init__.py`中添加路由处理函数
2. 创建对应的HTML模板，使用Tailwind样式
3. 更新导航菜单样式
4. 确保响应式设计在所有断点正常工作

### 媒体处理组件
```html
<!-- 视频播放器组件 -->
<div class="relative aspect-video bg-black rounded-lg overflow-hidden">
  <video class="w-full h-full object-contain" controls>
    <source src="{{ url_for('video_view', name=file.name) }}" type="video/mp4">
  </video>
  <div class="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity">
    <button class="btn-primary rounded-full p-3">
      <i data-feather="play" class="w-8 h-8"></i>
    </button>
  </div>
</div>

<!-- 图片网格组件 -->
<div class="media-grid">
  {% for image in images %}
  <div class="group relative aspect-square overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-800">
    <img src="{{ url_for('media_view', uri=image.path) }}" 
         alt="{{ image.name }}"
         class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
         loading="lazy">
    <div class="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-20 transition-all">
      <div class="absolute bottom-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button class="p-2 bg-white dark:bg-gray-800 rounded-full shadow-lg">
          <i data-feather="heart" class="w-4 h-4"></i>
        </button>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
```

### 交互组件
```html
<!-- 模态框组件 -->
<div id="modal" class="fixed inset-0 z-50 hidden items-center justify-center bg-black bg-opacity-50 backdrop-blur-sm">
  <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 transform transition-all">
    <div class="p-6">
      <h3 class="text-lg font-semibold mb-4">确认删除</h3>
      <p class="text-gray-600 dark:text-gray-300 mb-6">此操作不可恢复，确定要删除这个文件吗？</p>
      <div class="flex gap-3 justify-end">
        <button class="px-4 py-2 text-gray-500 hover:text-gray-700 transition-colors">取消</button>
        <button class="btn-primary">删除</button>
      </div>
    </div>
  </div>
</div>

<!-- 通知组件 -->
<div class="fixed top-4 right-4 z-50 max-w-sm transform transition-all duration-300 translate-x-full">
  <div class="bg-green-500 text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3">
    <i data-feather="check-circle" class="w-5 h-5"></i>
    <span>操作成功完成</span>
  </div>
</div>
```

## 性能优化

### CSS优化
- 使用Tailwind CSS v4的新引擎实现更快的构建速度
- 利用@layer指令组织样式，确保正确的级联顺序
- 使用自定义CSS变量实现主题切换
- 避免不必要的样式重复

### JavaScript优化
- 使用Intersection Observer API实现图片懒加载
- 利用CSS transforms和transitions创建流畅动画
- 事件委托减少事件监听器数量

## 迁移指南

### 从Bulma迁移到Tailwind
```html
<!-- Bulma风格 -->
<div class="container">
  <div class="columns">
    <div class="column is-two-thirds">
      <div class="card">
        <div class="card-content">
          <button class="button is-primary">按钮</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Tailwind风格 -->
<div class="container mx-auto px-4">
  <div class="flex flex-wrap -mx-2">
    <div class="w-full md:w-2/3 px-2">
      <div class="bg-white rounded-lg shadow-md">
        <div class="p-6">
          <button class="btn-primary">按钮</button>
        </div>
      </div>
    </div>
  </div>
</div>
```

### 构建配置
```json
// package.json
{
  "scripts": {
    "build-css": "tailwindcss -i ./tiklocal/static/app.css -o ./tiklocal/static/dist/app.css --watch",
    "build-css-prod": "tailwindcss -i ./tiklocal/static/app.css -o ./tiklocal/static/dist/app.css --minify"
  },
  "devDependencies": {
    "tailwindcss": "^4.0.0"
  }
}
```

## 安全考虑

### 文件系统安全
- 所有文件路径都要使用`pathlib.Path`
- 验证文件路径在媒体目录内
- 不允许访问系统敏感文件

### 输入验证
- URL参数要进行适当的编码/解码
- 文件名要进行安全性检查
- 防止XSS和CSRF攻击
- CSP头部配置确保样式安全

## 部署与维护

### 开发环境
```bash
# 安装Python依赖
poetry install
poetry run tiklocal /path/to/media

# 安装前端依赖和构建CSS
npm install
npm run build-css

# 或使用虚拟环境
python -m venv env
source env/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 生产环境
- 使用`npm run build-css-prod`构建优化的CSS
- 配置静态文件缓存策略
- 使用Waitress作为WSGI服务器
- 设置适当的日志级别

## 故障排除

### 常见问题
1. **样式不生效**: 检查Tailwind配置文件和构建过程
2. **暗色模式异常**: 验证CSS变量和data-theme属性
3. **响应式布局问题**: 检查断点和网格系统使用
4. **性能问题**: 考虑CSS文件大小和未使用的样式清理

### 调试技巧
- 使用浏览器开发者工具检查Tailwind类是否正确应用
- 利用Tailwind CSS IntelliSense插件提高开发效率
- 使用`@apply`指令时要注意样式优先级

## 代码提交规范

### 提交消息格式
```
feat: 使用Tailwind CSS v4重构界面组件
fix: 修复暗色模式下的样式问题
style: 优化响应式网格布局
refactor: 迁移Bulma组件到Tailwind
docs: 更新CSS框架文档
perf: 优化CSS构建性能
```

### 代码审查要点
- Tailwind类使用是否符合最佳实践
- 响应式设计在所有设备上是否正常
- 暗色模式切换是否流畅
- CSS文件大小是否在合理范围内
- 自定义组件是否遵循设计系统

---

遵循以上规则，确保TikLocal应用使用Tailwind CSS v4实现现代化、高性能的用户界面，保持简洁、稳定、交互友好的特性。 