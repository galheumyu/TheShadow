# Team setup / Windows launchers

See [QUICKSTART.md](QUICKSTART.md). Run start_camera.bat for automatic local environment setup. The original shadow folder is not required.

# 双手距离 → Godot 粒子变色

这是独立的 Godot 4 项目。摄像头识别两只真实手的掌心位置，计算二维间距，通过本机 UDP 4242 发给 Godot。无需 Arduino。距离不是厘米，也不能区分前后深度。

## 运行

在此文件夹打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r tracker\requirements.txt
.\.venv\Scripts\python.exe tracker\hand_distance.py
```

首次运行会下载 Google 官方 hand_landmarker.task 模型到 tracker 文件夹，需要联网。打开 Godot 4，导入 `godot/project.godot`，按 F6（当前场景）或 F5（项目）运行。两个程序都需要保持运行，先后顺序不限。

本机已安装虚拟环境时，直接运行第三行。相机被占用时先关闭其他使用相机的软件；相机选错可加 `--camera 1`。

让摄像头看清两位玩家各一只手，掌心朝向摄像头，尽量在同一个深度平面活动。检测到两只手会绘制掌心圆点和连线。靠近时粒子从蓝色渐变为橙色，分开时回到蓝色。

在**摄像头窗口**按键：

- N：双手靠近但仍能分别识别时，记录当前距离作为最近端点。
- F：双手分开时，记录最远端点。
- Q：退出。

只有两只手均被识别时才能校准，且近端必须小于远端。校准值打印在终端，默认不保存；下次可用 `--near 0.12 --far 0.65` 指定。距离单位是画面宽度比例，纵向已经做宽高比修正。

## 没有摄像头也能验证变色

```powershell
.\.venv\Scripts\python.exe tracker\hand_distance.py --simulate
```

这会自动循环发送远近数据。Ctrl+C 停止。不要同时运行模拟和摄像头发送器。只运行一个 Godot 接收实例，以免端口冲突。

## 与组员的自动生成形状粒子系统衔接

你负责输出“靠近程度”，组员负责粒子的位置、形状和动画。双方只需约定：`proximity` 从 0（远）到 1（近），`valid` 表示当前是否检测到两只手。

复制 `godot/distance_receiver.gd` 到组员的项目，新建一个普通 Node，挂上脚本。一个场景只保留一个接收器。接收器提供每帧信号：

```gdscript
distance_updated(proximity: float, valid: bool, distance_norm: float)
```

已经内置平滑处理、无效数据处理、断开超过 0.5 秒自动回落。丢失追踪时 `valid=false`、距离为 -1，颜色平滑回到远端。不能把追踪丢失解释为两手碰到一起。

### 组员用 GPUParticles2D / CPUParticles2D

另建普通 Node，挂 `particle_color_adapter.gd`，在 Inspector 指定：

- Receiver Path：上述接收器。
- Particles Path：组员的二维粒子节点。
- Far Color / Near Color：远近端点颜色。

适配器只写粒子节点的 `modulate`，不会修改发射位置、形状、数量或运动。基础粒子颜色设为白色，颜色效果最直接；已有彩色粒子会与此颜色相乘。不要再让其他脚本同时写同一节点的 modulate。

### 组员使用自定义 Shader / GPU 形状系统

让组员订阅信号，将数值传给他们的 ShaderMaterial：

```gdscript
@export var distance_receiver: HandDistanceReceiver
@export var particle_shader: ShaderMaterial

func _ready() -> void:
    distance_receiver.distance_updated.connect(_on_distance_updated)

func _on_distance_updated(value: float, valid: bool, distance: float) -> void:
    particle_shader.set_shader_parameter("hand_proximity", value)
```

组员在原有着色器中声明 `uniform float hand_proximity = 0.0;`，用 `mix(far_color, near_color, hand_proximity)` 得到颜色，再写入现有颜色输出。保留原来的形状计算、粒子透明度和纹理采样。若项目中多个对象共享同一材质，先将该材质设为独立资源。

三维粒子不能使用二维的 modulate 适配器，应在其绘制材质/自定义 Shader 上接入此参数。你的接收器无需改动。

## UDP 数据约定（JSON / UTF-8）

```json
{"version":1,"valid":true,"hand_count":2,"distance_norm":0.3,"proximity":0.66,"centers":[[0.3,0.5],[0.6,0.5]]}
```

- 接收地址：127.0.0.1:4242，仅本机通信。
- `distance_norm`：掌心间二维像素距离 / 画面宽度；无效时为 null。
- `proximity`：依据 near/far 线性映射并限制到 0～1，Python 发原始值，Godot 做平滑。
- `centers`：镜像后画面中掌心中心的归一化 x/y；不保证跨帧身份顺序，但两点间距不受顺序影响。
- 无法识别两只手时立即发送 `valid=false`；程序崩溃或关闭时由接收器超时处理。

## 展示限制

测量定义是“掌心到掌心”，不是指尖间隙。它不识别玩家身份，看到任意两只手都会计算，因此两位玩家最好各伸一只手。掌心相贴时距离也不一定为零。严重重叠、背手、太暗和投影闪烁可能造成丢失。先在实际投影灯光下测试；优先让相机从不易遮挡的位置看到真实手。前后移动或改变相机位置会改变二维距离的意义，需要重新校准。

## 参考

- [MediaPipe Python Hand Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python)
- [Godot PacketPeerUDP](https://docs.godotengine.org/en/stable/classes/class_packetpeerudp.html)
