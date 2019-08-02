Proof-of-concept implentation of dense framework against mobile flash wearout attack.
This implementation targets Samsung S6 smartphone, with Android version 6.0.1, and Linux kernel version 3.10.101.
The key components include:
* kernel_patch: kernel patch for Samsung S6 Android kernel ([link](https://bitbucket.org/arter97/android_kernel_samsung_exynos7420/src/g920fi/)).
* framework: defense framework with various rate-limiting algorithms.

For more details, please refer to our [MobiSys '19](https://www.sigmobile.org/mobisys/2019/) [paper](https://oscarlab.github.io/papers/mobisys19-wearout.pdf) and our [project page](https://oscarlab.github.io/projects/flashstorage/).