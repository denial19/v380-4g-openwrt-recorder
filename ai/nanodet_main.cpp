// V380 JSON adapter for the official NCNN NanoDet example (BSD-3-Clause).
// This file is appended to upstream nanodet.cpp after its visual UI demo is removed.
#include <unistd.h>
#include <stdio.h>
#include <vector>

int main(int argc, char** argv)
{
    if (argc != 3) {
        fprintf(stderr, "Usage: %s /absolute/frame.jpg /absolute/model-directory\n", argv[0]);
        return 2;
    }
    cv::Mat image = cv::imread(argv[1], 1);
    if (image.empty()) {
        fprintf(stderr, "Cannot read image: %s\n", argv[1]);
        return 3;
    }
    if (chdir(argv[2]) != 0) {
        perror("Cannot open model directory");
        return 4;
    }
    std::vector<Object> objects;
    if (detect_nanodet(image, objects) != 0) return 5;
    printf("{\"width\":%d,\"height\":%d,\"model\":\"nanodet_m\",\"objects\":[", image.cols, image.rows);
    bool first = true;
    for (size_t i = 0; i < objects.size(); ++i) {
        const Object& o = objects[i];
        int k = o.label;
        if (k != 0 && k != 2 && k != 3 && k != 5 && k != 7) continue;
        const char* name = k == 0 ? "person" : (k == 2 ? "car" : (k == 3 ? "motorcycle" : (k == 5 ? "bus" : "truck")));
        if (!first) printf(",");
        first = false;
        printf("{\"label\":\"%s\",\"class_id\":%d,\"confidence\":%.5f,\"bbox\":[%.2f,%.2f,%.2f,%.2f]}",
               name, k, o.prob, o.rect.x, o.rect.y, o.rect.width, o.rect.height);
    }
    puts("]}");
    return 0;
}
