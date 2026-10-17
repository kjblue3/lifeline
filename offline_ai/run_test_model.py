
import torch
from executorch.runtime import Runtime

runtime = Runtime.get()

program = runtime.load_program("test_model.pte")
method = program.load_method("forward")

inputs = [
    torch.tensor([1.0, 2.0]),
    torch.tensor([3.0, 4.0]),
]

outputs = method.execute(inputs)

print("ExecuTorch output:", outputs)
print("Expected result: [4.0, 6.0]")
