# Real repository manifest matrix

Pinned upstream manifest extracts only: tests reconstruct the copied manifest paths, not entire upstream repositories. No upstream source, build, dependency installation, or external skill discovery is executed; results do not certify whole-repository behavior.

Offline verification checks pinned identities, copied manifest/license SHA-256 values, expected technologies, selected language/build skills, documentation classification, workspace language isolation and read-only proposals.

| Repository | Pinned commit | Manifest | Result |
| --- | --- | --- | --- |
| [google/googletest](https://github.com/google/googletest/tree/a8380b01a25ebdb130097b607b3afed2a58d04ba) | `a8380b01a25ebdb130097b607b3afed2a58d04ba` | `CMakeLists.txt` | PASS |
| [p11-glue/p11-kit](https://github.com/p11-glue/p11-kit/tree/e5ee541ae14ec2e3324fdf393cb069163ee9666b) | `e5ee541ae14ec2e3324fdf393cb069163ee9666b` | `meson.build` | PASS |
| [flutter/samples](https://github.com/flutter/samples/tree/9df2cac15cc3d28a51aace018ad822387d30ac72) | `9df2cac15cc3d28a51aace018ad822387d30ac72` | `form_app/pubspec.yaml` | PASS |
| [apple/swift-argument-parser](https://github.com/apple/swift-argument-parser/tree/38ca4eceb349155836701b88da3e0986eb9d1e1c) | `38ca4eceb349155836701b88da3e0986eb9d1e1c` | `Package.swift` | PASS |
| [elixir-plug/plug](https://github.com/elixir-plug/plug/tree/0d5b5eacb93b6de8f89454452cb232aa57672733) | `0d5b5eacb93b6de8f89454452cb232aa57672733` | `mix.exs` | PASS |
| [JuliaLang/Example.jl](https://github.com/JuliaLang/Example.jl/tree/82d1224c32990c0105898fa44009864f5648e98d) | `82d1224c32990c0105898fa44009864f5648e98d` | `Project.toml` | PASS |
| [r-lib/cli](https://github.com/r-lib/cli/tree/633bc27770f3357238d0f797132ad000cd1a8eb4) | `633bc27770f3357238d0f797132ad000cd1a8eb4` | `DESCRIPTION` | PASS |
| [pallets/flask](https://github.com/pallets/flask/tree/49943b5a94413a530761350f04e896f76e8d620e) | `49943b5a94413a530761350f04e896f76e8d620e` | `pyproject.toml` | PASS |
| [BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep/tree/91f5d22ef48bde459d90a8c7dbeab416e97d0f2b) | `91f5d22ef48bde459d90a8c7dbeab416e97d0f2b` | `Cargo.toml` | PASS |
| [gin-gonic/gin](https://github.com/gin-gonic/gin/tree/0f09c3a9b4626d9fe9979cf4d0521d6ae32ab646) | `0f09c3a9b4626d9fe9979cf4d0521d6ae32ab646` | `go.mod` | PASS |
| [vitejs/vite](https://github.com/vitejs/vite/tree/483512809bbdb399d66be59af0f5aeb01ccb7181) | `483512809bbdb399d66be59af0f5aeb01ccb7181` | `packages/vite/package.json` | PASS |
| [spring-guides/gs-rest-service](https://github.com/spring-guides/gs-rest-service/tree/e15fec6773dc1eb6028055630e3e68cbd8653240) | `e15fec6773dc1eb6028055630e3e68cbd8653240` | `complete/pom.xml` | PASS |
| [rails/rails](https://github.com/rails/rails/tree/2f4d502119c0d0cf9500a2d49a00eea9c557bacb) | `2f4d502119c0d0cf9500a2d49a00eea9c557bacb` | `Gemfile` | PASS |
| [laravel/framework](https://github.com/laravel/framework/tree/7d6d8e86138e9dcc250a29bd72cfe5d5dd7b3d6c) | `7d6d8e86138e9dcc250a29bd72cfe5d5dd7b3d6c` | `composer.json` | PASS |

All copied files retain their upstream license in `fixtures/real-repositories/<slug>/LICENSE.txt`; each provenance record links the exact pinned original files. Refresh is explicit (`python tools/verify_real_repositories.py --refresh`) and uses a request limit, per-request timeout, total deadline and file-size cap. Default verification never accesses the network.

GitHub license detection returned `NOASSERTION` for the following notices. Their applicable licenses were reviewed against the pinned upstream text; each review is bound to the copied notice's SHA-256:

- [flutter/samples](https://github.com/flutter/samples/blob/9df2cac15cc3d28a51aace018ad822387d30ac72/LICENSE), BSD-3-Clause: Reviewed upstream LICENSE: source code uses the opening BSD 3-Clause notice; the complete copied LICENSE also retains upstream font OFL terms. Only the source manifest is extracted.
- [elixir-plug/plug](https://github.com/elixir-plug/plug/blob/0d5b5eacb93b6de8f89454452cb232aa57672733/LICENSE), Apache-2.0: Reviewed upstream LICENSE explicitly states Licensed under the Apache License, Version 2.0 and links its terms.
- [r-lib/cli](https://github.com/r-lib/cli/blob/633bc27770f3357238d0f797132ad000cd1a8eb4/LICENSE), MIT: Upstream DESCRIPTION declares License: MIT + file LICENSE; the copied original LICENSE retains YEAR and COPYRIGHT HOLDER. The upstream MIT declaration supplies the license terms.
- [BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep/blob/91f5d22ef48bde459d90a8c7dbeab416e97d0f2b/UNLICENSE), Unlicense: Reviewed upstream UNLICENSE grants unrestricted public-domain use and redistribution. The complete notice is copied.
