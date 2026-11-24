def matrix_multiply(A, B):
    if not A or not B:
        return []
    # BUG: no shape validation
    result = [[0.0] * len(B[0]) for _ in range(len(A))]
    for i in range(len(A)):
        for j in range(len(B[0])):
            for k in range(len(B)):
                result[i][j] += A[i][k] * B[k][j]
    return result

def transpose(M):
    if not M:
        return M
    return [[row[i] for row in M] for i in range(len(M[0]))]
