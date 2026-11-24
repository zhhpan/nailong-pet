# 奶龙 · ChatGPT 工作宠物

一只陪你做研究的奶龙。平时它睁着眼睛轻轻呼吸，等你回应时会摊开小爪子，遇到难题则抱臂托腮。笑得最开心时，它双手捂着肚子弯下腰，圆脑袋也跟着笑出了一个尖。

![奶龙的九种动作和环顾动画](assets/nailong.gif)

[下载宠物精灵图 PNG](https://github.com/zhhpan/nailong-pet/releases/latest/download/nailong.png) · [单看捧腹大笑](assets/laugh.gif) · [完整 MP4 预览](assets/nailong.mp4) · [查看动画原画](source/)

## 在 ChatGPT 中使用

1. 下载上面的 PNG 原文件，也可以从仓库的 `assets/nailong.png` 获取。
2. 在已启用 Pets 的 ChatGPT 工作模式中附上这张 PNG，发送「请校验这张 Work Pets v2 精灵图，用它创建一个叫『奶龙』的宠物，并设为当前宠物。」

请上传透明 PNG 原图。上方的 GIF 带有动作名称和背景色，供预览使用。

## 待机呼吸与捧腹大笑

v1.3 的跳跃动作从圆头站姿开始。奶龙捂住肚子轻跳，落地大笑时头顶向一侧收成尖角，随后站直，恢复圆头。已有奶龙的用户可以附上新版 PNG，请 Pets 更新现有奶龙的精灵图。[查看 v1.2 与 v1.3 的跳跃对比](assets/jumping-v1.2-v1.3.gif)

宠物的六帧待机动作让头和肚皮随呼吸轻轻起伏。按 Windows 版 Codex 26.1117.4957.0 的播放时序，待机一轮 6.60 秒，跳跃一轮 0.84 秒。也可以回看上一版对呼吸和动作节奏的调整。[v1.1 与 v1.2 的待机对比](assets/idle-v1.1-v1.2.gif) · [v1.1 与 v1.2 的跳跃对比](assets/jumping-v1.1-v1.2.gif)

页首总览和独立的大笑预览使用 **25 fps** 运动补帧。独立动画保留全部八张大笑原画，一个循环有 39 帧，时长 1.56 秒。透明 WebP 可以叠在自己的画面上。[下载透明大笑动图](https://github.com/zhhpan/nailong-pet/releases/latest/download/laugh.webp) · [观看大笑视频](assets/laugh.mp4)

## 修改某一帧

在仓库根目录运行以下命令，安装 Pillow 并拆出各个动作的透明帧。

```sh
python -m pip install -r requirements.txt
python tools/frames.py split assets/nailong.png build/frames
```

例如，要修改托腮的动作，编辑 `build/frames/running/` 中的 PNG。每格保持 **192 × 208 像素**，保留透明背景，把改好的帧重新拼成一张图。

```sh
python tools/frames.py pack build/frames build/nailong-edited.png
```

两个命令都需要新的输出路径。保持各帧原样拆出、再拼回时，整张图的 RGBA 像素与原图一致。

### 重新导出 25 fps 预览

先安装 FFmpeg，使终端能运行 `ffmpeg`。以下命令会为每个动作生成 GIF 和 MP4，同时将独立大笑动画导出为透明 WebP。需要改动捧腹大笑的姿势时，可以编辑 `source/laugh-keys.png` 中对应的透明帧。

```sh
python -m pip install -r requirements-preview.txt
python tools/preview.py assets/nailong.png build/preview --laugh-strip source/laugh-keys.png
```

## 动画布局

精灵图共 8 列、11 行，大小为 **1536 × 2288 像素**。前九行依次是待机、向右跑、向左跑、挥手、跳跃、沮丧、等待回应、抱臂思考和检查结果，共 57 帧。最后两行是 16 个注视方向，从正上方开始，每格顺时针转 22.5°。另外 15 格完全透明。

如果想从原画调整动作幅度或重新取景，`source/` 中有用 ImageGen 制作的全身定稿、动作条和四向注视参考，均以无损 WebP 保存。[原画文件与帧序说明](source/README.md)

## 许可

这是非官方奶龙同人作品。仓库中的脚本、文档及贡献者有权授权的原创动画制作部分采用 MIT 许可证。奶龙角色形象及相关标识的权利归各自权利人所有。[许可证全文](LICENSE)
