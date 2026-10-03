"""gpu_view.py - GPU camera compositor for the adi storyboard board.

Takes the (at most two) board tiles that are in view, plus the camera path
for this frame (1 sample at rest, several sub-frame samples while panning ->
motion blur), and produces the final W x H frame on the GPU:

  * tiles are uploaded as textures; the shader maps each output pixel to the
    board, so the pan, the vertical drift, the 2x supersample downscale and the
    motion blur all happen on the GPU (bilinear taps at exact 2:1 give a
    proper 2x2 box resolve when the camera is at rest);
  * the orange progress line along the bottom is drawn in the same pass.

If OpenGL is unavailable, callers fall back to the CPU (PIL) path.
"""
import numpy as np

try:
    import moderngl
except ImportError:                      # pragma: no cover
    moderngl = None

MAX_SAMPLES = 16

_VERT = """
#version 330
in vec2 pos;
void main() { gl_Position = vec4(pos, 0.0, 1.0); }
"""

_FRAG = """
#version 330
uniform sampler2D tex0;
uniform sampler2D tex1;
uniform int n0;
uniform int n1;
uniform float lefts[16];
uniform float dys[16];
uniform int ns;
uniform float prog;
uniform vec3 bg;
uniform vec3 bar;
uniform vec2 out_size;
uniform float tile_p;
uniform float tile_gap;
uniform float tile_mv;
uniform float ss;
uniform vec2 tex_size;
out vec4 color;

vec3 fetch(float bx, float by) {
    float shifted = bx + tile_gap * 0.5;
    int n = int(floor(shifted / tile_p));
    vec2 tx = vec2((shifted - float(n) * tile_p) * ss, (by + tile_mv) * ss);
    vec2 uv = tx / tex_size;
    if (n == n0) return texture(tex0, uv).rgb;
    if (n == n1) return texture(tex1, uv).rgb;
    return bg;
}

void main() {
    float px = gl_FragCoord.x;
    float py = gl_FragCoord.y;   // fbo.read() returns rows bottom-first, so this yields top-first output
    vec3 acc = vec3(0.0);
    for (int j = 0; j < ns; j++) {
        acc += fetch(lefts[j] + px, dys[j] + py);
    }
    acc /= float(ns);
    if (py > out_size.y - 9.0 && px < out_size.x * prog) acc = bar;
    color = vec4(acc, 1.0);
}
"""


class GpuView:
    def __init__(self, W, H, SS, P, GAP, MV, bg, bar):
        if moderngl is None:
            raise RuntimeError("moderngl not installed")
        self.W, self.H = W, H
        self.ctx = moderngl.create_standalone_context(require=330)
        self.prog = self.ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)
        quad = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4")
        self.vbo = self.ctx.buffer(quad.tobytes())
        self.vao = self.ctx.simple_vertex_array(self.prog, self.vbo, "pos")
        self.tex_w, self.tex_h = int(P * SS), int((H + 2 * MV) * SS)
        self.tex = []
        for _ in range(2):
            t = self.ctx.texture((self.tex_w, self.tex_h), 3)
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
            t.repeat_x = t.repeat_y = False
            self.tex.append(t)
        self.fbo = self.ctx.simple_framebuffer((W, H), components=3)
        pr = self.prog
        pr["out_size"].value = (float(W), float(H))
        pr["tile_p"].value = float(P)
        pr["tile_gap"].value = float(GAP)
        pr["tile_mv"].value = float(MV)
        pr["ss"].value = float(SS)
        pr["tex_size"].value = (float(self.tex_w), float(self.tex_h))
        pr["bg"].value = tuple(c / 255.0 for c in bg)
        pr["bar"].value = tuple(c / 255.0 for c in bar)
        pr["tex0"].value = 0
        pr["tex1"].value = 1

    def render(self, tiles, lefts, dys, prog):
        """tiles: {board_index: PIL RGB image (P*SS x (H+2MV)*SS)} (1 or 2 entries).
        lefts/dys: camera samples (board x of the view's left edge, vertical offset).
        Returns W*H*3 raw RGB bytes, top row first."""
        items = list(tiles.items())[:2]
        ns = [-1, -1]
        for i, (n, img) in enumerate(items):
            self.tex[i].write(img.tobytes())
            ns[i] = int(n)
        pr = self.prog
        pr["n0"].value = ns[0]
        pr["n1"].value = ns[1]
        k = min(len(lefts), MAX_SAMPLES)
        pr["ns"].value = k
        pr["lefts"].value = tuple(float(v) for v in lefts[:k]) + (0.0,) * (MAX_SAMPLES - k)
        pr["dys"].value = tuple(float(v) for v in dys[:k]) + (0.0,) * (MAX_SAMPLES - k)
        pr["prog"].value = float(prog)
        self.tex[0].use(0)
        self.tex[1].use(1)
        self.fbo.use()
        self.fbo.clear(0.0, 0.0, 0.0, 1.0)
        self.vao.render(moderngl.TRIANGLE_STRIP)
        return self.fbo.read(components=3)

    def close(self):
        self.ctx.release()
