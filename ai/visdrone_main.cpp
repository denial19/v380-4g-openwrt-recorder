// VisDrone YOLO11s NCNN parking-only detector for OpenWrt ARM64 (CPU-only).
// The bundled NCNN runtime is BSD-3-Clause; pretrained Ultralytics YOLO11n weights are AGPL-3.0.
// Expects VisDrone 11 classes, out0 = (4+11) x N. Supports 640 and 960 model exports.
#include "net.h"
#if defined(USE_NCNN_SIMPLEOCV)
#include "simpleocv.h"
#else
#include <opencv2/core/core.hpp>
#include <opencv2/highgui/highgui.hpp>
#endif
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

struct Box { float x, y, w, h, score; int label; };
static float iou(const Box& a, const Box& b) {
    const float x0 = std::max(a.x, b.x), y0 = std::max(a.y, b.y);
    const float x1 = std::min(a.x + a.w, b.x + b.w), y1 = std::min(a.y + a.h, b.y + b.h);
    const float inter = std::max(0.f, x1-x0) * std::max(0.f, y1-y0);
    const float den = a.w*a.h + b.w*b.h - inter;
    return den > 0 ? inter / den : 0.f;
}
static float clip(float v, float lo, float hi) { return std::min(hi, std::max(lo, v)); }
static const char* classname(int c) {
    switch(c) {
        case 0: return "person";    // VisDrone pedestrian
        case 1: return "person";    // VisDrone people
        case 3: return "car";
        case 4: return "van";
        case 5: return "truck";
        case 8: return "bus";
        default: return nullptr;
    }
}
static bool veh(int c) { return c==3 || c==4 || c==5 || c==8; }
int main(int argc, char** argv) {
    if (argc != 3 && argc != 4) {
        std::fprintf(stderr, "Usage: %s image.jpg model_directory [threshold 0.05..0.95]\n", argv[0]);
        return 2;
    }
    float threshold = 0.25f;
    if (argc == 4) {
        char* end = nullptr;
        threshold = std::strtof(argv[3], &end);
        if (!end || *end || !std::isfinite(threshold) || threshold < .05f || threshold > .95f) {
            std::fprintf(stderr, "Invalid confidence threshold\n"); return 2;
        }
    }
    cv::Mat image = cv::imread(argv[1], 1);
    if (image.empty() || image.cols < 32 || image.rows < 32) {
        std::fprintf(stderr, "Cannot decode image or dimensions too small\n"); return 3;
    }
    const int width = image.cols, height = image.rows;
    std::ifstream meta(std::string(argv[2])+"/model_size.txt");
    int size = 0;
    if (!(meta >> size) || (size != 640 && size != 960)) {
        std::fprintf(stderr, "Missing or invalid model_size.txt, expected 640 or 960\n"); return 4;
    }
    const float scale = std::min((float)size/width, (float)size/height);
    const int rw = std::max(1, (int)std::round(width*scale));
    const int rh = std::max(1, (int)std::round(height*scale));
    const int left = (size-rw)/2, top = (size-rh)/2;
    const int right = size-rw-left, bottom = size-rh-top;
    ncnn::Mat input = ncnn::Mat::from_pixels_resize(image.data, ncnn::Mat::PIXEL_BGR2RGB,
                                                      width, height, rw, rh);
    ncnn::Mat padded;
    ncnn::copy_make_border(input, padded, top, bottom, left, right,
                           ncnn::BORDER_CONSTANT, 114.f);
    const float norm[3] = {1.f/255.f, 1.f/255.f, 1.f/255.f};
    padded.substract_mean_normalize(nullptr, norm);
    ncnn::Net net;
    net.opt.use_vulkan_compute = false;
    net.opt.num_threads = 1;
    net.opt.use_fp16_packed = false;
    net.opt.use_fp16_storage = false;
    net.opt.use_fp16_arithmetic = false;
    const std::string dir = argv[2];
    if (net.load_param((dir + "/model.ncnn.param").c_str()) != 0 ||
        net.load_model((dir + "/model.ncnn.bin").c_str()) != 0) {
        std::fprintf(stderr, "Cannot load YOLO11n model\n"); return 4;
    }
    ncnn::Extractor ex = net.create_extractor();
    if (ex.input("in0", padded) != 0) {
        std::fprintf(stderr, "Failed to provide input in0\n"); return 5;
    }
    ncnn::Mat out;
    if (ex.extract("out0", out) != 0) {
        std::fprintf(stderr, "Cannot extract out0\n"); return 5;
    }
    // The exported VisDrone model encodes 11 classes; anchors depend on input size.
    // A format change must fail closed rather than silently report no cars.
    if (out.dims != 2 || out.w != (size/8)*(size/8) + (size/16)*(size/16) + (size/32)*(size/32) || out.h != 15 || out.elemsize != 4u) {
        std::fprintf(stderr, "Unexpected NCNN shape: dims=%d w=%d h=%d elemsize=%zu\n",
                     out.dims, out.w, out.h, out.elemsize);
        return 6;
    }
    const float *xc = out.row(0), *yc = out.row(1), *wc = out.row(2), *hc = out.row(3);
    std::vector<Box> raw;
    raw.reserve(64);
    for (int i=0;i<out.w;i++) {
        int label = -1;
        float confidence = threshold;
        for (const int cls: {0, 1, 3, 4, 5, 8}) {
            float score = out.row(4+cls)[i];
            if (std::isfinite(score) && score > confidence) { label=cls; confidence=score; }
        }
        if (label < 0) continue;
        float x0 = (xc[i]-wc[i]*.5f-left)/scale;
        float y0 = (yc[i]-hc[i]*.5f-top)/scale;
        float x1 = (xc[i]+wc[i]*.5f-left)/scale;
        float y1 = (yc[i]+hc[i]*.5f-top)/scale;
        x0=clip(x0,0,(float)width); x1=clip(x1,0,(float)width);
        y0=clip(y0,0,(float)height); y1=clip(y1,0,(float)height);
        if (!(x1>x0+1 && y1>y0+1)) continue;
        raw.push_back({x0,y0,x1-x0,y1-y0,confidence,label});
    }
    std::sort(raw.begin(), raw.end(), [](const Box&a,const Box&b){return a.score>b.score;});
    std::vector<Box> objects;
    for (const Box& obj : raw) {
        bool suppressed=false;
        for (const Box& kept : objects) {
            if ((kept.label==obj.label || (veh(kept.label) && veh(obj.label)) ||
                 ((kept.label<=1) && (obj.label<=1))) && iou(obj,kept)>.45f) {suppressed=true;break;}
        }
        if (!suppressed) objects.push_back(obj);
        if (objects.size() >= 80) break;
    }
    std::printf("{\"width\":%d,\"height\":%d,\"model\":\"visdrone-yolo11s\",\"objects\":[",width,height);
    for (size_t i=0;i<objects.size();i++) {
        const Box& b=objects[i];
        if (i) std::printf(",");
        std::printf("{\"label\":\"%s\",\"class_id\":%d,\"confidence\":%.5f,\"bbox\":[%.2f,%.2f,%.2f,%.2f]}",
                    classname(b.label),b.label,b.score,b.x,b.y,b.w,b.h);
    }
    std::puts("]}");
    return 0;
}
